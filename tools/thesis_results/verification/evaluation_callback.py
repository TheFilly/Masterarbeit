"""Pipeline-Callback fuer den qualitativen V-001-bis-V-011-Lauf."""

from __future__ import annotations

import filecmp
import json
import shutil
import uuid
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from threading import Lock

import injection_pipeline.api as pipeline_api
from injection_pipeline.api import inject_function

from .bundle_validation import BundleValidation, validate_run_bundle
from .case_outcomes import (
    ArtifactStatus,
    CaseOutcome,
    CaseResult,
)
from .evaluation_runner import PlannedCase

_RUN_TIMESTAMP = datetime(2026, 9, 2, 12, 0, 0)
_API_LOCK = Lock()
_SUPPORTED_DOCUMENT_TYPES = {"dcm", "jpg", "jpeg"}
_INPUT_OUTPUT_POLICY = "tolerated_reencoding_with_warning"
REQUIRES_SEQUENTIAL = True


# Input: Geplanter Fall und vom Runner zugewiesenes Fallverzeichnis.
# Output: Nachweisbares CaseResult mit validiertem Bundle oder kontrollierter Ablehnung.
# Die Funktion schreibt ausschliesslich in `output`, nutzt stabile Fallwerte und
# ueberlaesst ROI-/Input-Output-Pruefungen dem bestehenden EvaluationRunner.
def run_case(case: PlannedCase, output: Path) -> CaseResult:
    """Fuehrt genau eine deterministische DICOM-/JPG-Injektion aus."""
    profile = case.profile
    if profile is not None and profile.supported is False:
        reason = profile.profile_reason or "Dokumentrepraesentation nicht unterstuetzt"
        return CaseResult(
            case.case_id,
            CaseOutcome.REJECTED,
            case.source_fingerprint,
            artifact_status=ArtifactStatus.MISSING,
            error_code="unsupported_representation",
            expected_ground_truth_files=0,
            profile=profile,
            rejection_type="unsupported",
            rejection_reason=reason,
            rejection_evidence={
                "callback_status": "unsupported",
                "reason_code": "unsupported_representation",
                "reason": reason,
            },
        )

    document_type = case.document_type.casefold()
    if document_type not in _SUPPORTED_DOCUMENT_TYPES:
        if case.expected_rejection:
            reason = (
                "Der qualitative Pipeline-Callback unterstuetzt im Scope nur "
                "DICOM und JPG."
            )
            return CaseResult(
                case.case_id,
                CaseOutcome.REJECTED,
                case.source_fingerprint,
                artifact_status=ArtifactStatus.MISSING,
                error_code="contract_rejection",
                expected_ground_truth_files=0,
                profile=profile,
                rejection_type="contract_rejection",
                rejection_reason=reason,
                rejection_evidence={
                    "callback_status": "contract_rejection",
                    "reason_code": "contract_violation",
                    "reason": reason,
                    "input_output_policy": _INPUT_OUTPUT_POLICY,
                },
            )
        return _unexpected_result(case, "unsupported_format")

    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        return _unexpected_result(case, "existing_output_directory")
    output.parent.mkdir(parents=True, exist_ok=True)
    transaction = _new_staging_path(output.parent)
    pipeline_output = transaction / "p"
    staging = transaction / "b"
    value = f"EVAL-{case.case_id.upper()}"
    try:
        transaction.mkdir()
        staging.mkdir()
        pipeline_output.mkdir()
        with _API_LOCK:
            previous_output_dir = pipeline_api.DEFAULT_OUTPUT_DIR  # type: ignore[attr-defined]
            pipeline_api.DEFAULT_OUTPUT_DIR = pipeline_output  # type: ignore[attr-defined]
            try:
                _injected_path, ground_truth_path = inject_function(
                    category="PatientID",
                    value=value,
                    prefix="ID: ",
                    suffix="",
                    handwritten=False,
                    documentType="jpg" if document_type == "jpeg" else document_type,
                    output_dir=pipeline_output,
                    seed=_case_seed(case),
                    input_path=case.source,
                    rotation_degrees=(
                        profile.rotation_degrees
                        if profile is not None and profile.rotation_degrees is not None
                        else 0
                    ),
                    run_timestamp=_RUN_TIMESTAMP,
                )
            finally:
                pipeline_api.DEFAULT_OUTPUT_DIR = previous_output_dir  # type: ignore[attr-defined]
        _materialize_bundle(ground_truth_path, staging, case.source)
        validation = validate_run_bundle(
            staging,
            workspace=output.parent.parent,
            source_fingerprint=case.source_fingerprint,
        )
        if not validation.valid:
            return _result_from_validation(case, staging, validation)
        if output.exists():
            if not output.is_dir() or any(output.iterdir()):
                raise FileExistsError(f"Ziel bereits belegt: {output}")
            output.rmdir()
        staging.rename(output)
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        return _unexpected_result(case, type(error).__name__)
    finally:
        _cleanup_staging(transaction)

    validation = validate_run_bundle(
        output,
        workspace=output.parent.parent,
        source_fingerprint=case.source_fingerprint,
    )
    valid = validation.valid
    return CaseResult(
        case.case_id,
        CaseOutcome.SUCCESSFUL if valid else CaseOutcome.UNEXPECTED_FAILED,
        case.source_fingerprint,
        artifact_status=ArtifactStatus.VALID if valid else ArtifactStatus.INCONSISTENT,
        error_code=None if valid else "invalid_bundle",
        ground_truth_files=validation.physical_ground_truth_files,
        expected_ground_truth_files=1,
        unparseable_artifacts=validation.unparseable_artifacts,
        invalid_annotations=validation.invalid_annotations,
        path_collisions=validation.path_collisions,
        profile=profile,
        artifact_paths=tuple(
            str(path.relative_to(output))
            for path in sorted(output.rglob("*"))
            if path.is_file()
        ),
    )


# Input: Geplanter Fall, Staging-Verzeichnis und BundleValidation.
# Output: Unerwartetes CaseResult mit den belegten Bundle-Befunden.
# Das Staging wird nach der Rückgabe durch `run_case` verworfen und nie als
# unvollständiger Ziel-Fallordner veröffentlicht.
def _result_from_validation(
    case: PlannedCase, staging: Path, validation: BundleValidation
) -> CaseResult:
    return CaseResult(
        case.case_id,
        CaseOutcome.UNEXPECTED_FAILED,
        case.source_fingerprint,
        artifact_status=ArtifactStatus.INCONSISTENT,
        error_code="invalid_bundle",
        ground_truth_files=validation.physical_ground_truth_files,
        expected_ground_truth_files=1,
        unparseable_artifacts=validation.unparseable_artifacts,
        invalid_annotations=validation.invalid_annotations,
        path_collisions=validation.path_collisions,
        profile=case.profile,
        artifact_paths=tuple(
            str(path.relative_to(staging))
            for path in sorted(staging.rglob("*"))
            if path.is_file()
        ),
    )


# Input: exportierte Ground Truth und Ziel-Fallordner.
# Output: Keine Rueckgabe; das vollstaendige Bundle liegt im Zielordner.
# Die Public API erzeugt den vollstaendigen Run historisch unter `output/` und
# exportiert zwei Dateien. Diese Funktion kopiert den Run lokal und normalisiert
# nur generierte Referenzen fuer die Workspace-Grenzpruefung.
def _materialize_bundle(ground_truth_path: Path, output: Path, source: Path) -> None:
    payload = json.loads(ground_truth_path.read_text(encoding="utf-8-sig"))
    internal_output = Path(str(payload["output_file"])).parent
    if not internal_output.is_absolute():
        internal_output = Path.cwd() / internal_output
    run_id = payload.get("run_id")
    if isinstance(run_id, str):
        candidate = ground_truth_path.parent / run_id
        if candidate.is_dir():
            internal_output = candidate
    if not internal_output.is_dir():
        raise FileNotFoundError(f"Internes API-Bundle fehlt: {internal_output}")
    _materialize_internal_bundle(internal_output, output, source)


# Input: vorhandener API-Runordner, Ziel-Fallordner und externe Quelle.
# Output: Keine Rueckgabe; das Bundle wird kopiert und intern referenziert.
# Das Ziel ist ein neuer Publish-Ordner; vorhandene Dateien werden nie ueberschrieben.
def _materialize_internal_bundle(
    internal_output: Path, output: Path, source: Path
) -> None:
    output.mkdir(parents=True, exist_ok=True)
    for artifact in internal_output.iterdir():
        if artifact.is_file():
            destination = output / artifact.name
            if destination.exists():
                if not filecmp.cmp(artifact, destination, shallow=False):
                    raise FileExistsError(f"Artefakt bereits vorhanden: {destination}")
                continue
            shutil.copy2(artifact, destination)
    for name in ("ground_truth.json", "run_manifest.json"):
        path = output / name
        record = json.loads(path.read_text(encoding="utf-8-sig"))
        _localize_generated_references(record, source)
        path.write_text(
            json.dumps(record, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


# Input: ausschliesslich der eigene Transaktionsordner des aktuellen Falls.
# Output: Keine Rueckgabe; best-effort wird der Transaktionsordner entfernt.
# Fehler beim Aufraeumen werden bewusst nicht als Pipelinefehler weitergegeben.
# Input: Fallordner-Elternpfad.
# Output: Eindeutiger, noch nicht belegter Geschwisterpfad.
# Der Pfad wird nicht angelegt; dadurch bleibt die atomare Publikation dem
# aufrufenden Ablauf vorbehalten.
def _new_staging_path(parent: Path) -> Path:
    """Erzeugt einen eindeutigen, noch nicht belegten Geschwisterpfad."""
    return (parent / f".tmp-eval-{uuid.uuid4().hex[:8]}").resolve()


# Input: Ausschliesslich ein eigener Stagingpfad dieses Falls.
# Output: Keine Rueckgabe; best-effort wird der Stagingpfad entfernt.
# Fehler beim Aufraeumen werden bewusst nicht als Pipelinefehler weitergegeben.
def _cleanup_staging(staging: Path) -> None:
    if not staging.exists():
        return
    with suppress(OSError):
        shutil.rmtree(staging, ignore_errors=True)


# Input: JSON-RunRecord mit absoluten oder internen Artefaktpfaden.
# Output: Keine Rueckgabe; erzeugte Artefakte werden auf Bundle-Dateinamen relativiert.
# Die externe Quelle bleibt unveraendert, damit der Source-Fingerprint weiterhin
# gegen das Originaldokument geprueft werden kann.
def _localize_generated_references(record: dict[str, object], source: Path) -> None:
    record["source_file"] = str(source.resolve())
    for key in ("output_file", "preview_file", "annotated_preview_file"):
        value = record.get(key)
        if isinstance(value, str):
            record[key] = Path(value).name
    annotations = record.get("dicom_tag_annotations")
    if isinstance(annotations, list):
        for annotation in annotations:
            if isinstance(annotation, dict):
                value = annotation.get("output_file")
                if isinstance(value, str):
                    annotation["output_file"] = Path(value).name
                annotation["source_file"] = str(source.resolve())


# Input: Geplanter Fall mit stabilem case_id.
# Output: Deterministisch abgeleiteter Seed fuer die einzelne Injektion.
# Die Ableitung verhindert, dass die Fallreihenfolge den Zufallsstrom eines
# einzelnen Falls veraendert.
def _case_seed(case: PlannedCase) -> int:
    return 42 + sum((index + 1) * ord(char) for index, char in enumerate(case.case_id))


# Input: Geplanter Fall und maschinenlesbarer Fehlercode.
# Output: Explizit als unerwartet fehlgeschlagen markiertes CaseResult.
# Es werden keine Artefakte behauptet; ein eventuell vom API-Aufruf erzeugtes
# Teilbundle bleibt fuer den Runner als Fehlerdiagnose sichtbar.
def _unexpected_result(case: PlannedCase, error_code: str) -> CaseResult:
    return CaseResult(
        case.case_id,
        CaseOutcome.UNEXPECTED_FAILED,
        case.source_fingerprint,
        artifact_status=ArtifactStatus.MISSING,
        error_code=error_code,
        profile=case.profile,
    )
