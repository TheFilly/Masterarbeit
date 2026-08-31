"""Datenmodelle und Bilanzregeln der qualitativen Evaluation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class CaseOutcome(StrEnum):
    """Terminale Fallklassifikation."""

    SUCCESSFUL = "successful"
    REJECTED = "rejected"
    UNEXPECTED_FAILED = "unexpected_failed"


def classify_failure(
    *,
    documented_rejection: bool,
    planned_negative: bool,
    failure_kind: str = "unparseable",
) -> CaseOutcome:
    """Ordnet einen Fehler gemaess dem Evaluationsvertrag terminal ein.

    Dokumentierte Vertragsablehnungen werden als `rejected` erfasst. Nicht
    parsbare Eingaben duerfen nur bei expliziter Negativfall-Markierung so
    klassifiziert werden; alle anderen Fehler sind unerwartet.
    """
    if failure_kind not in {
        "unparseable",
        "contract_rejection",
        "unsupported",
        "unexpected",
    }:
        raise ValueError(f"Unbekannte Fehlerart: {failure_kind}")
    if documented_rejection or failure_kind in {"contract_rejection", "unsupported"}:
        return CaseOutcome.REJECTED
    if planned_negative and failure_kind == "unparseable":
        return CaseOutcome.REJECTED
    return CaseOutcome.UNEXPECTED_FAILED


class ArtifactStatus(StrEnum):
    """Status der erzeugten Evaluationsartefakte."""

    VALID = "valid"
    MISSING = "missing"
    UNPARSEABLE = "unparseable"
    INCONSISTENT = "inconsistent"


class ProfileStatus(StrEnum):
    """Vollstaendigkeit des Eingabeprofils."""

    COMPLETE = "complete"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"
    NON_PARSEABLE = "non_parseable"


@dataclass(frozen=True)
class EvaluationConfig:
    """Reproduzierbare Ausfuehrungseinstellungen."""

    seed: int = 42
    workers: int = 1
    mode: str = "sequential"
    block_size: int = 100
    render_parameters: dict[str, Any] = field(default_factory=dict)

    # Input: Konfiguration.
    # Output: Stabiler Fingerprint ohne Pfad- oder Zeitabhaengigkeit.
    # Der Fingerprint verweigert keine unbekannten Parameter, sondern macht sie
    # fuer Restart-Pruefungen explizit vergleichbar.
    def fingerprint(self) -> str:
        payload = asdict(self)
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()


@dataclass(frozen=True)
class CaseProfile:
    """Profilmerkmale einer geplanten Fallinstanz."""

    case_id: str
    source_fingerprint: str
    document_type: str | None = None
    photometry: str | None = None
    width: int | None = None
    height: int | None = None
    size_class: str | None = None
    frame_mode: str | None = None
    supported: bool | None = None
    expected_schema_fields: tuple[str, ...] = ()
    present_structured_fields: tuple[str, ...] = ()
    used_structured_fields: tuple[str, ...] = ()
    missing_expected_fields: tuple[str, ...] = ()
    profile_status: ProfileStatus = ProfileStatus.UNAVAILABLE
    profile_reason: str | None = None
    placement_mode: str | None = None
    rotation_degrees: int | None = None
    font_or_renderer: str | None = None
    handwriting_options: dict[str, Any] = field(default_factory=dict)
    render_options: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CaseResult:
    """Ein terminal klassifizierter Evaluationsfall."""

    case_id: str
    outcome: CaseOutcome
    source_fingerprint: str
    artifact_status: ArtifactStatus = ArtifactStatus.MISSING
    error_code: str | None = None
    ground_truth_files: int = 0
    expected_ground_truth_files: int = 1
    unparseable_artifacts: int = 0
    invalid_annotations: int = 0
    path_collisions: int = 0
    clipping_errors: int = 0
    geometry_errors: int = 0
    input_output_differences: int = 0
    output_bytes: int = 0
    profile: CaseProfile | None = None
    artifact_paths: tuple[str, ...] = ()
    block_number: int | None = None
    input_output_status: str | None = None
    input_output_reason: str | None = None
    pixel_measurement_status: str = "not_executed"
    pixel_measurement_reason: str | None = (
        "Keine gerenderte BBox bzw. kein Pixel-Sampler bereitgestellt."
    )
    rejection_type: str | None = None
    rejection_reason: str | None = None
    rejection_evidence: dict[str, Any] = field(default_factory=dict)


# Input: Ein terminales Ergebnis mit Ablehnungsmetadaten.
# Output: True nur bei strukturell validierter Ablehnungsevidenz.
def has_valid_rejection_evidence(result: CaseResult) -> bool:
    evidence = result.rejection_evidence
    if not result.rejection_type or not result.rejection_reason:
        return False
    if result.rejection_type == "unsupported":
        profile = result.profile
        return (
            profile is not None
            and profile.supported is False
            and evidence.get("callback_status") == "unsupported"
            and evidence.get("reason_code") in {
                "unsupported_format",
                "unsupported_representation",
            }
            and evidence.get("reason") == result.rejection_reason
        )
    if result.rejection_type == "contract_rejection":
        return (
            evidence.get("callback_status") == "contract_rejection"
            and evidence.get("reason_code") == "contract_violation"
            and evidence.get("reason") == result.rejection_reason
        )
    if result.rejection_type == "planned_negative_unparseable":
        return (
            result.profile is not None
            and result.profile.supported is True
            and evidence.get("callback_status") == "unparseable"
            and evidence.get("reason_code") == "planned_negative_unparseable"
        )
    return False


@dataclass
class Balance:
    """Bilanz eines Blocks oder eines Gesamtlaufs."""

    planned: int = 0
    successful: int = 0
    rejected: int = 0
    unexpected_failed: int = 0
    ground_truth_present: int = 0
    ground_truth_missing: int = 0
    unparseable_artifacts: int = 0
    invalid_annotations: int = 0
    path_collisions: int = 0
    clipping_errors: int = 0
    geometry_errors: int = 0
    input_output_differences: int = 0
    completed_documents: int = 0
    in_progress_documents: int = 0
    open_documents: int = 0
    output_bytes: int = 0
    elapsed_seconds: float = 0.0
    throughput_documents_per_second: float = 0.0
    peak_memory_bytes: int = 0
    peak_memory_definition: str = "process_maximum"
    worker_execution_status: str = "single_process"
    worker_execution_reason: str | None = (
        "Der Harness verarbeitet im aktuellen Modus nicht parallel."
    )
    execution_measurement_status: str = "single_process_only"
    execution_measurement_reason: str = "worker_execution_not_implemented"
    seed: int = 42
    workers: int = 1
    actual_worker_count: int = 1
    mode: str = "sequential"
    block_number: int = 0
    block_size: int = 0
    block_status: str = "completed"
    abort_reason: str | None = None

    # Input: terminale Fallresultate und geplante Fallanzahl.
    # Output: Vollstaendig aggregierte Bilanz.
    # Die Funktion wirft bei doppelten oder unbekannten Fall-IDs einen Fehler.
    @classmethod
    def from_results(cls, results: list[CaseResult], planned: int) -> Balance:
        if len({result.case_id for result in results}) != len(results):
            raise ValueError("Jeder Fall darf nur eine terminale Klassifikation haben.")
        counts = {outcome: 0 for outcome in CaseOutcome}
        for result in results:
            if result.outcome == CaseOutcome.SUCCESSFUL and (
                result.artifact_status != ArtifactStatus.VALID
                or result.ground_truth_files != result.expected_ground_truth_files
            ):
                raise ValueError(
                    "Erfolgreicher Fall hat nicht die erwartete Ground Truth."
                )
            counts[result.outcome] += 1
        if sum(counts.values()) > planned:
            raise ValueError("Mehr terminale Faelle als geplant.")
        return cls(
            planned=planned,
            successful=counts[CaseOutcome.SUCCESSFUL],
            rejected=counts[CaseOutcome.REJECTED],
            unexpected_failed=counts[CaseOutcome.UNEXPECTED_FAILED],
            ground_truth_present=sum(r.ground_truth_files for r in results),
            ground_truth_missing=sum(
                max(r.expected_ground_truth_files - r.ground_truth_files, 0)
                for r in results
            ),
            unparseable_artifacts=sum(r.unparseable_artifacts for r in results),
            invalid_annotations=sum(r.invalid_annotations for r in results),
            path_collisions=sum(r.path_collisions for r in results),
            clipping_errors=sum(r.clipping_errors for r in results),
            geometry_errors=sum(r.geometry_errors for r in results),
            input_output_differences=sum(
                r.input_output_status == "different" for r in results
            ),
            completed_documents=len(results),
            open_documents=planned - len(results),
            output_bytes=sum(r.output_bytes for r in results),
        )

    # Input: Bilanz.
    # Output: Keine Rueckgabe; Fehler bei unerklaerter Fallzahldifferenz.
    # Erfolgreiche Bundles muessen genau die erwartete Ground-Truth-Menge haben.
    def assert_complete(self) -> None:
        if self.planned != self.successful + self.rejected + self.unexpected_failed:
            raise ValueError("Fallbilanz ist nicht vollstaendig.")
        if self.completed_documents != self.planned or self.open_documents != 0:
            raise ValueError("Nicht alle geplanten Faelle sind terminal klassifiziert.")
        if self.successful and self.ground_truth_missing:
            raise ValueError("Erfolgreiche Faelle haben fehlende Ground Truth.")
