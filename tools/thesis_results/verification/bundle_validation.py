"""Fachliche Konsistenzpruefung von Run-Bundles."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydicom.errors import InvalidDicomError
from tools.thesis_results.coordinate_validation import coordinate_validation

from injection_pipeline.models import load_run_record


@dataclass(frozen=True)
class BundleIssue:
    """Ein maschinenlesbarer Bundle-Befund."""

    code: str
    path: str
    detail: str


@dataclass(frozen=True)
class BundleValidation:
    """Getrennte Statuswerte der Bundle-Pruefung."""

    valid: bool
    issues: tuple[BundleIssue, ...]
    ground_truth_files: int = 0
    parseable_ground_truth_files: int = 0
    unparseable_artifacts: int = 0
    unavailable_artifacts: int = 0
    invalid_annotations: int = 0
    path_collisions: int = 0
    semantic_consistent: bool = False
    expected_references_present: bool = False
    physical_ground_truth_files: int = 0


def _inside(path: Path, root: Path) -> bool:
    """Prueft die Workspace-Grenze."""
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _record_paths(record: Any) -> list[tuple[Path, bool]]:
    """Liest Referenzen und markiert erzeugte Artefaktpfade."""
    names = ("source_file", "output_file", "preview_file", "annotated_preview_file")
    paths = [(Path(getattr(record, name)), name != "source_file") for name in names]
    for annotation in record.dicom_tag_annotations:
        paths.extend(
            (
                (Path(annotation.source_file), False),
                (Path(annotation.output_file), True),
            )
        )
    return paths


def _resolve_reference(path: Path, run_dir: Path) -> Path:
    """Loest relative Record-Pfade relativ zum Bundle auf."""
    return path if path.is_absolute() else run_dir / path


def _sha256(path: Path) -> str:
    """Berechnet den Fingerprint einer externen Eingabedatei."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _document_parseable(path: Path) -> tuple[bool, str | None]:
    """Prueft bekannte Dokumentformate ohne neue Abhaengigkeit."""
    try:
        if path.suffix.casefold() == ".dcm":
            import pydicom

            dataset = pydicom.dcmread(path)
            _ = dataset.pixel_array
        elif path.suffix.casefold() in {".jpg", ".jpeg", ".png"}:
            from PIL import Image

            with Image.open(path) as image:
                image.verify()
        elif path.suffix.casefold() == ".pdf":
            if shutil.which("pdftoppm") is None:
                return False, "pdftoppm nicht verfuegbar"
            from pypdf import PdfReader

            reader = PdfReader(str(path))
            if not reader.pages:
                return False, "PDF enthaelt keine Seiten"
            with tempfile.TemporaryDirectory(prefix="pdf-validation-") as directory:
                for page_number in range(len(reader.pages)):
                    coordinate_validation.render_pdf_page(
                        path,
                        page_number,
                        72,
                        Path(directory) / f"page-{page_number}.png",
                    )
        else:
            return False, "unsupported_output_format"
    except (
        OSError,
        EOFError,
        RuntimeError,
        ValueError,
        TypeError,
        InvalidDicomError,
    ):
        return False, "Ausgabedokument ist nicht parsbar"
    return True, None


def _validate_annotation_references(record: Any, path: Path) -> list[BundleIssue]:
    """Prueft Identitaet, Segmente und Koordinaten der Annotationen."""
    issues: list[BundleIssue] = []
    for annotation in record.dicom_tag_annotations:
        if annotation.identity_id != record.identity_id:
            issues.append(
                BundleIssue(
                    "identity_reference",
                    str(path),
                    "Tagannotation verweist auf andere Identitaet",
                )
            )
    for annotation in record.span_annotations:
        if annotation.start < 0 or annotation.end < annotation.start:
            issues.append(
                BundleIssue("invalid_annotation", str(path), "Ungueltiges Textsegment")
            )
    for annotation in record.box_annotations:
        if annotation.frame_index < 0 or len(annotation.corners.root) != 4:
            issues.append(
                BundleIssue("invalid_annotation", str(path), "Ungueltige Boxannotation")
            )
        if not annotation.text or not annotation.rendered_text:
            issues.append(
                BundleIssue("invalid_annotation", str(path), "Leerer Annotationstext")
            )
    return issues


# Input: Run-Verzeichnis und optionaler erlaubter Evaluation-Workspace.
# Output: Parsbarkeits-, Referenz- und Semantikstatus des Bundles.
# Ground Truth zaehlt erst nach erfolgreichem JSON- und RunRecord-Parsing als parsbar.
def validate_run_bundle(
    run_dir: Path,
    workspace: Path | None = None,
    source_fingerprint: str | None = None,
) -> BundleValidation:
    issues: list[BundleIssue] = []
    gt_path, manifest_path = (
        run_dir / "ground_truth.json",
        run_dir / "run_manifest.json",
    )
    payloads: dict[str, dict[str, Any]] = {}
    unparseable = 0
    unavailable = 0
    for label, path in (("ground_truth", gt_path), ("manifest", manifest_path)):
        if not path.is_file():
            issues.append(BundleIssue("missing_artifact", str(path), f"{label} fehlt"))
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8-sig"))
            if not isinstance(value, dict):
                raise ValueError("JSON ist kein Objekt")
            payloads[label] = value
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
            unparseable += 1
            issues.append(BundleIssue("unparseable_artifact", str(path), str(error)))
    if (
        set(payloads) == {"ground_truth", "manifest"}
        and payloads["ground_truth"] != payloads["manifest"]
    ):
        issues.append(
            BundleIssue(
                "inconsistent_artifact",
                str(manifest_path),
                "Ground Truth und Manifest unterscheiden sich",
            )
        )
    parseable_gt = 0
    semantic = False
    expected = False
    invalid_annotations = 0
    if "ground_truth" in payloads:
        try:
            record = load_run_record(gt_path)
            parseable_gt = 1
            payload = payloads["ground_truth"]
            if (
                payload.get("record_type") != record.record_type
                or payload.get("schema_version") != record.schema_version
            ):
                issues.append(
                    BundleIssue(
                        "invalid_record_metadata",
                        str(gt_path),
                        "record_type oder schema_version stimmt nicht",
                    )
                )
            if not record.identity_id or not record.run_id:
                issues.append(
                    BundleIssue(
                        "invalid_record_metadata",
                        str(gt_path),
                        "run_id oder identity_id fehlt",
                    )
                )
            root = (workspace or run_dir).resolve()
            manifest_record = None
            if "manifest" in payloads:
                try:
                    manifest_record = load_run_record(manifest_path)
                except (OSError, ValueError, TypeError, AttributeError) as error:
                    issues.append(
                        BundleIssue(
                            "invalid_manifest_record", str(manifest_path), str(error)
                        )
                    )
            if manifest_record is not None and manifest_record.model_dump(
                mode="json"
            ) != record.model_dump(mode="json"):
                issues.append(
                    BundleIssue(
                        "manifest_ground_truth_difference",
                        str(manifest_path),
                        "Manifest und Ground Truth sind semantisch verschieden",
                    )
                )
            references = [
                (_resolve_reference(path, run_dir), generated)
                for path, generated in _record_paths(record)
            ]
            keys = [str(path.resolve()) for path, _ in references]
            if len(set(keys)) != len(keys):
                issues.append(
                    BundleIssue(
                        "duplicate_artifact_path",
                        str(gt_path),
                        "Referenzpfad innerhalb des Bundles doppelt",
                    )
                )
            for reference, generated in references:
                if generated and not _inside(reference, root):
                    issues.append(
                        BundleIssue(
                            "path_outside_workspace",
                            str(reference),
                            "Pfad liegt ausserhalb des Evaluation-Workspace",
                        )
                    )
                if not reference.is_file():
                    issues.append(
                        BundleIssue(
                            "missing_referenced_artifact",
                            str(reference),
                            "Referenzierte Datei fehlt",
                        )
                    )
                if (
                    not generated
                    and source_fingerprint
                    and reference.is_file()
                    and _sha256(reference) != source_fingerprint
                ):
                    issues.append(
                        BundleIssue(
                            "source_fingerprint_mismatch",
                            str(reference),
                            "Externe Quelle stimmt nicht mit dem Input-Fingerprint "
                            "ueberein",
                        )
                    )
                if generated and reference.is_file():
                    parseable, reason = _document_parseable(reference)
                    if not parseable:
                        issue_code = (
                            "unavailable_artifact"
                            if reason == "pdftoppm nicht verfuegbar"
                            else "unparseable_artifact"
                        )
                        if issue_code == "unavailable_artifact":
                            unavailable += 1
                        else:
                            unparseable += 1
                        issues.append(
                            BundleIssue(
                                issue_code,
                                str(reference),
                                reason or "Artefakt ist nicht parsbar",
                            )
                        )
            annotation_issues = _validate_annotation_references(record, gt_path)
            issues.extend(annotation_issues)
            invalid_annotations = sum(
                issue.code == "invalid_annotation" for issue in annotation_issues
            )
            expected = all(
                reference.is_file() and (not generated or _inside(reference, root))
                for reference, generated in references
            )
            semantic = not any(
                issue.code
                in {
                    "invalid_record_metadata",
                    "identity_reference",
                    "invalid_annotation",
                    "inconsistent_artifact",
                    "invalid_manifest_record",
                    "manifest_ground_truth_difference",
                }
                for issue in issues
            )
        except (OSError, ValueError, TypeError, AttributeError) as error:
            unparseable += 1
            issues.append(BundleIssue("invalid_run_record", str(gt_path), str(error)))
    return BundleValidation(
        valid=(
            not any(issue.code != "unavailable_artifact" for issue in issues)
            and parseable_gt == 1
        ),
        issues=tuple(issues),
        ground_truth_files=parseable_gt,
        parseable_ground_truth_files=parseable_gt,
        unparseable_artifacts=unparseable,
        unavailable_artifacts=unavailable,
        invalid_annotations=invalid_annotations,
        path_collisions=sum(
            issue.code == "duplicate_artifact_path" for issue in issues
        ),
        semantic_consistent=semantic,
        expected_references_present=expected,
        physical_ground_truth_files=int(gt_path.is_file()),
    )


# Input: mehrere Bundle-Verzeichnisse im selben Workspace.
# Output: globale Kollisionen aller referenzierten Artefaktpfade.
# Die Funktion liest nur bereits vorhandene, parsbare RunRecords.
def find_bundle_path_collisions(bundle_dirs: list[Path]) -> tuple[BundleIssue, ...]:
    seen: dict[str, Path] = {}
    issues: list[BundleIssue] = []
    for bundle in bundle_dirs:
        try:
            record = load_run_record(bundle / "ground_truth.json")
        except (OSError, ValueError, TypeError):
            continue
        for path, _ in [
            *_record_paths(record),
            (bundle / "ground_truth.json", True),
            (bundle / "run_manifest.json", True),
        ]:
            path = _resolve_reference(path, bundle)
            key = str(path.resolve())
            previous = seen.get(key)
            if previous is not None and previous != bundle:
                issues.append(
                    BundleIssue("path_collision", key, f"Kollision mit {previous}")
                )
            seen[key] = bundle
    return tuple(issues)
