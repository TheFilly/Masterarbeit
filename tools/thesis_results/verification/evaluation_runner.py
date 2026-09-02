"""Ausfuehrbarer, transaktionaler Harness fuer qualitative Evaluation."""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import tracemalloc
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from threading import Lock
from typing import Any, cast

from .bundle_validation import validate_run_bundle
from .case_outcomes import (
    ArtifactStatus,
    Balance,
    CaseOutcome,
    CaseProfile,
    CaseResult,
    EvaluationConfig,
    ProfileStatus,
    classify_failure,
    has_valid_rejection_evidence,
)


class _CancelledBeforeStart(Exception):
    """Interner Marker fuer einen vor dem Callback abgebrochenen Future."""


@dataclass(frozen=True)
class PlannedCase:
    """Stabile Fallbeschreibung unabhaengig vom Ausgabepfad."""

    case_id: str
    source: Path
    source_fingerprint: str
    document_type: str
    profile: CaseProfile | None = None
    expected_rejection: bool = False
    planned_negative: bool = False


@dataclass(frozen=True)
class BlockSummary:
    """Persistierter Zwischenstand mit globalen und lokalen Falllisten."""

    block_number: int
    block_size: int
    status: str
    balance: Balance
    terminal_case_ids: tuple[str, ...]
    in_progress_case_ids: tuple[str, ...]
    open_case_ids: tuple[str, ...]
    seed: int
    workers: int
    mode: str
    elapsed_seconds: float
    output_bytes: int
    peak_memory_bytes: int
    abort_reason: str | None = None


def source_fingerprint(path: Path) -> str:
    """Berechnet einen SHA-256-Fingerprint einer Quelle."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_atomic(path: Path, payload: Any) -> None:
    """Schreibt eine JSON-Projektion atomar."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def _directory_size(root: Path) -> int:
    """Misst alle vor Cleanup erzeugten Dateien im Evaluation-Workspace."""
    return sum(path.stat().st_size for path in root.rglob("*") if path.is_file())


# Input: Fallbundle.
# Output: Bytes deklarierter Dokument-/Ground-Truth-Artefakte ohne Temporaries.
def _declared_output_audit(root: Path) -> tuple[int, tuple[str, ...]]:
    if not root.is_dir():
        return 0, ()
    references: set[Path] = {
        Path("ground_truth.json"),
        Path("run_manifest.json"),
    }
    try:
        payload = json.loads(
            (root / "ground_truth.json").read_text(encoding="utf-8-sig")
        )

        def collect_references(value: object) -> None:
            if isinstance(value, dict):
                for key, nested in value.items():
                    if key.endswith("_file") and isinstance(nested, str):
                        if key != "source_file":
                            candidate = Path(nested)
                            references.add(candidate)
                    else:
                        collect_references(nested)
            elif isinstance(value, list):
                for item in value:
                    collect_references(item)

        collect_references(payload)
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError):
        pass
    resolved: set[Path] = set()
    unexpected: list[str] = []
    root_resolved = root.resolve()
    for name in references:
        candidate = name if name.is_absolute() else root / name
        try:
            resolved_candidate = candidate.resolve()
            if root_resolved not in resolved_candidate.parents:
                unexpected.append(str(name))
            elif resolved_candidate.is_file():
                resolved.add(resolved_candidate)
            else:
                unexpected.append(str(name))
        except OSError:
            unexpected.append(str(name))
    declared_names = {path.relative_to(root_resolved).as_posix() for path in resolved}
    for file_path in root.rglob("*"):
        if file_path.is_file():
            relative = file_path.resolve().relative_to(root_resolved).as_posix()
            if relative not in declared_names and not relative.startswith("."):
                unexpected.append(relative)
    return sum(path.stat().st_size for path in resolved), tuple(sorted(set(unexpected)))


def _declared_output_bytes(root: Path) -> int:
    """Gibt die Bytes deklarierter, innerhalb des Bundles liegender Dateien zurück."""
    return _declared_output_audit(root)[0]


def _fingerprint_cases(cases: list[PlannedCase]) -> str:
    payload = [
        {
            "case_id": c.case_id,
            "source_fingerprint": c.source_fingerprint,
            "document_type": c.document_type,
        }
        for c in cases
    ]
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


class EvaluationRunner:
    """Fuehrt Faelle aus und veroeffentlicht nur vollstaendige Commit-Pakete."""

    checkpoint_schema_version = "3.0"

    def __init__(self, workspace: Path, config: EvaluationConfig) -> None:
        if config.block_size < 1 or config.workers < 1:
            raise ValueError("block_size und workers muessen positiv sein.")
        if config.mode not in {"sequential", "parallel"}:
            raise ValueError("mode muss 'sequential' oder 'parallel' sein.")
        self.workspace = workspace
        self.config = config
        self.results_dir = workspace / "case-results"
        self.checkpoint_path = workspace / "checkpoint.json"
        self.manifest_path = workspace / "input-manifest.json"

    # Input: Geplante Faelle.
    # Output: Persistierte Input-Liste und Fingerprint.
    # Das Manifest ist die unveraenderliche Restart-Grundlage.
    def prepare(self, cases: Iterable[PlannedCase]) -> list[PlannedCase]:
        planned = list(cases)
        if len({case.case_id for case in planned}) != len(planned):
            raise ValueError("case_id muss innerhalb eines Laufs eindeutig sein.")
        payload = {
            "input_fingerprint": _fingerprint_cases(planned),
            "cases": [asdict(case) for case in planned],
        }
        if self.manifest_path.exists():
            old = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            if old.get("input_fingerprint") != payload["input_fingerprint"]:
                raise ValueError("Input-Fingerprint passt nicht zum bestehenden Lauf.")
        else:
            _write_atomic(self.manifest_path, payload)
        return planned

    # Input: Fallliste, Callback und optionaler Restart.
    # Output: Vollstaendige oder bei Abbruch persistierte Bilanz.
    # Blockresultate, Fallresultate und Checkpoint werden als ein Paket veroeffentlicht.
    def run(
        self,
        cases: Iterable[PlannedCase],
        callback: Callable[[PlannedCase, Path], CaseResult],
        *,
        resume: bool = False,
    ) -> Balance:
        planned = self.prepare(cases)
        previous = None
        if resume:
            self._adopt_orphan_commit()
        if resume and self.checkpoint_path.exists():
            raw_checkpoint = json.loads(
                self.checkpoint_path.read_text(encoding="utf-8")
            )
            if raw_checkpoint.get("config_fingerprint") != self.config.fingerprint():
                raise ValueError(
                    "Konfiguration passt nicht zum bestehenden Checkpoint."
                )
            previous = self._load_checkpoint()
        if previous and previous.get("config_fingerprint") != self.config.fingerprint():
            raise ValueError("Konfiguration passt nicht zum bestehenden Checkpoint.")
        completed = (
            set(
                previous.get(
                    "terminal_case_ids", previous.get("completed_case_ids", [])
                )
            )
            if previous
            else set()
        )
        known = {case.case_id for case in planned}
        if not completed <= known:
            raise ValueError("Checkpoint enthaelt unbekannte case_id.")
        results = self._results_from_checkpoint(previous)
        if {result.case_id for result in results} != completed:
            raise ValueError("Checkpoint und Fallresultate sind nicht konsistent.")
        start = time.perf_counter()
        tracemalloc.start()
        run_worker_ids: set[int] = set()
        run_worker_lock = Lock()
        try:
            for offset in range(0, len(planned), self.config.block_size):
                block_number = offset // self.config.block_size + 1
                block = planned[offset : offset + self.config.block_size]
                pending = [case for case in block if case.case_id not in completed]
                if not pending:
                    continue
                block_start = time.perf_counter()
                block_results: list[CaseResult] = []
                started_case_ids: set[str] = set()
                started_lock = Lock()
                block_worker_ids: set[int] = set()
                block_worker_lock = Lock()
                abort_requested = threading.Event()
                try:

                    def process_case(
                        case: PlannedCase,
                        current_block: int = block_number,
                        tracked_case_ids: set[str] = started_case_ids,
                        tracking_lock: Lock = started_lock,
                        abort_event: threading.Event = abort_requested,
                        tracked_worker_ids: set[int] = block_worker_ids,
                        worker_ids_lock: Lock = block_worker_lock,
                        all_worker_ids: set[int] = run_worker_ids,
                        all_worker_ids_lock: Lock = run_worker_lock,
                    ) -> CaseResult:
                        output = self.results_dir / case.case_id
                        with tracking_lock:
                            if abort_event.is_set():
                                raise _CancelledBeforeStart(case.case_id)
                            tracked_case_ids.add(case.case_id)
                        worker_id = threading.get_ident()
                        with worker_ids_lock:
                            tracked_worker_ids.add(worker_id)
                        with all_worker_ids_lock:
                            all_worker_ids.add(worker_id)
                        try:
                            if (
                                case.profile is not None
                                and case.profile.profile_status
                                == ProfileStatus.NON_PARSEABLE
                            ):
                                result = CaseResult(
                                    case.case_id,
                                    CaseOutcome.UNEXPECTED_FAILED,
                                    case.source_fingerprint,
                                    artifact_status=ArtifactStatus.UNPARSEABLE,
                                    error_code="non_parseable_input",
                                    unparseable_artifacts=1,
                                    profile=case.profile,
                                )
                            else:
                                result = callback(case, output)
                        except Exception as error:
                            kind = getattr(error, "failure_kind", "unexpected")
                            result = CaseResult(
                                case.case_id,
                                classify_failure(
                                    documented_rejection=False,
                                    planned_negative=case.planned_negative,
                                    failure_kind=str(kind),
                                ),
                                case.source_fingerprint,
                                error_code=(
                                    str(kind)
                                    if str(kind)
                                    in {
                                        "contract_rejection",
                                        "unsupported",
                                        "unparseable",
                                    }
                                    else type(error).__name__
                                ),
                            )
                        if result.case_id != case.case_id:
                            raise ValueError("Callback lieferte eine falsche case_id.")
                        declared_bytes, unexpected_files = _declared_output_audit(
                            output
                        )
                        result = replace(
                            result,
                            block_number=current_block,
                            profile=result.profile or case.profile,
                            output_bytes=max(result.output_bytes, declared_bytes),
                            path_collisions=result.path_collisions
                            + len(unexpected_files),
                        )
                        return self._validate_callback_result(case, result, output)

                    def execute_case(
                        case: PlannedCase,
                        abort_event: threading.Event = abort_requested,
                    ) -> CaseResult:
                        try:
                            return process_case(case)
                        except BaseException:
                            abort_event.set()
                            raise

                    if self.config.mode == "parallel" and self.config.workers > 1:
                        executor = ThreadPoolExecutor(
                            max_workers=self.config.workers,
                            thread_name_prefix="evaluation-case",
                        )
                        futures = [
                            executor.submit(execute_case, case) for case in pending
                        ]
                        try:
                            # Die Ergebnisreihenfolge folgt weiterhin der Planung.
                            block_results = [future.result() for future in futures]
                        except BaseException:
                            # Noch nicht gestartete Futures dürfen nach einem Abbruch
                            # nicht nachträglich in_progress werden.
                            executor.shutdown(wait=False, cancel_futures=True)
                            block_results = []
                            for _case, future in zip(pending, futures, strict=True):
                                if not future.done() or future.cancelled():
                                    continue
                                try:
                                    block_results.append(future.result())
                                except BaseException:
                                    continue
                            raise
                        else:
                            executor.shutdown(wait=True)
                    else:
                        for case in pending:
                            block_results.append(process_case(case))
                except BaseException as error:
                    terminal = completed | {r.case_id for r in block_results}
                    in_progress = [
                        c.case_id
                        for c in pending
                        if c.case_id in started_case_ids and c.case_id not in terminal
                    ]
                    open_ids = [
                        c.case_id
                        for c in planned
                        if c.case_id not in terminal and c.case_id not in in_progress
                    ]
                    summary = self._summary(
                        block_number,
                        len(block),
                        "interrupted",
                        results + block_results,
                        terminal,
                        in_progress,
                        open_ids,
                        block_start,
                        str(error),
                        len(block_worker_ids) if block_worker_ids else 1,
                    )
                    self._write_interrupted(summary, results + block_results, planned)
                    raise
                candidate = results + block_results
                terminal = completed | {r.case_id for r in block_results}
                summary = self._summary(
                    block_number,
                    len(block),
                    "completed",
                    candidate,
                    terminal,
                    [],
                    [c.case_id for c in planned if c.case_id not in terminal],
                    block_start,
                    None,
                    len(block_worker_ids) if block_worker_ids else 1,
                )
                self._commit_block(summary, candidate)
                results, completed = candidate, terminal
        finally:
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
        final = Balance.from_results(results, len(planned))
        final.elapsed_seconds = time.perf_counter() - start
        final.throughput_documents_per_second = (
            len(results) / final.elapsed_seconds if final.elapsed_seconds else 0.0
        )
        final.seed, final.workers, final.mode, final.block_size = (
            self.config.seed,
            self.config.workers,
            self.config.mode,
            self.config.block_size,
        )
        final.actual_worker_count = (
            len(run_worker_ids)
            if self.config.mode == "parallel" and self.config.workers > 1
            else 1
        )
        final.peak_memory_bytes = peak
        final.peak_memory_definition = (
            "tracemalloc_process_peak; Worker-Speicher nicht aggregiert"
        )
        final.worker_execution_status = (
            "single_process_measured"
            if self.config.mode == "sequential" or self.config.workers == 1
            else "thread_pool_measured"
        )
        final.worker_execution_reason = (
            "Einzelprozess wurde gemessen."
            if self.config.mode == "sequential" or self.config.workers == 1
            else "ThreadPoolExecutor mit konfigurierter Workerzahl wurde ausgefuehrt."
        )
        final.execution_measurement_status = (
            "single_process_measured"
            if self.config.mode == "sequential" or self.config.workers == 1
            else "thread_pool_tracemalloc_measured"
        )
        final.execution_measurement_reason = (
            (
                "Peak-Memory gilt fuer den Prozess und aggregiert "
                "Python-Allokationen aller Threads."
            )
            if self.config.mode == "parallel" and self.config.workers > 1
            else "Peak-Memory gilt fuer den Einzelprozess."
        )
        final.output_bytes = sum(result.output_bytes for result in results)
        final.input_output_differences = sum(
            result.input_output_status == "different" for result in results
        )
        final.assert_complete()
        _write_atomic(self.workspace / "run-summary.json", asdict(final))
        self._write_coordinate_metrics(planned, results)
        _write_atomic(
            self.workspace / "evaluation-metrics.json",
            {
                "output_volume_definition": (
                    "Summe der pro Fall erzeugten Dateien vor Evaluation-Cleanup"
                ),
                "peak_memory_definition": final.peak_memory_definition,
                "output_bytes": final.output_bytes,
                "peak_memory_bytes": final.peak_memory_bytes,
            },
        )
        return final

    # Input: Geplante Faelle und terminale CaseResults des abgeschlossenen Laufs.
    # Output: Automatisch verknuepfte Fall-/Block-Koordinatenmetriken.
    # Pixelmetriken bleiben ohne belastbare gerenderte BBox bewusst unbekannt.
    def _write_coordinate_metrics(
        self, cases: list[PlannedCase], results: list[CaseResult]
    ) -> None:
        from .coordinate_adapter import aggregate_coordinate_cases

        planned_by_id = {case.case_id: case for case in cases}
        coordinate_cases: list[
            tuple[Path, CaseProfile]
            | tuple[Path, CaseProfile, int]
            | tuple[Path, CaseProfile, CaseResult]
        ] = []
        for result in results:
            case = planned_by_id.get(result.case_id)
            profile = result.profile or (case.profile if case else None)
            ground_truth = self.results_dir / result.case_id / "ground_truth.json"
            if (
                result.outcome == CaseOutcome.SUCCESSFUL
                and profile is not None
                and ground_truth.is_file()
            ):
                coordinate_cases.append((ground_truth, profile, result))
        metrics = aggregate_coordinate_cases(
            coordinate_cases,
            self.config.block_size,
            pixel_sampler=self._coordinate_pixel_sampler(coordinate_cases),
            pixel_sample_rate=float(
                self.config.render_parameters.get("pixel_sample_rate", 1.0)
            ),
            pixel_seed=self.config.seed,
        )
        _write_atomic(self.workspace / "coordinate-metrics.json", metrics)

    # Input: Koordinatenfaelle mit ihren Ground-Truth-Pfaden.
    # Output: Deterministischer Sampler fuer vorhandene gerenderte Ausgaben.
    def _coordinate_pixel_sampler(self, cases: list[Any]) -> Any:
        from .coordinate_adapter import measure_rendered_annotation

        output_by_ground_truth: dict[Path, Path] = {}
        for ground_truth, _profile, _result in cases:
            try:
                payload = json.loads(ground_truth.read_text(encoding="utf-8-sig"))
                output_file = payload.get("output_file")
                if isinstance(output_file, str):
                    candidate = Path(output_file)
                    output_by_ground_truth[ground_truth] = (
                        candidate
                        if candidate.is_absolute()
                        else ground_truth.parent / candidate
                    )
            except (OSError, UnicodeError, json.JSONDecodeError):
                continue

        def sample(
            ground_truth: Path, row: dict[str, Any], profile: CaseProfile
        ) -> dict[str, Any] | None:
            rendered = output_by_ground_truth.get(ground_truth)
            if rendered is None or not rendered.is_file():
                return None
            try:
                return measure_rendered_annotation(
                    ground_truth,
                    rendered,
                    int(row.get("annotation_index", 0)),
                    width=int(profile.width or row["width"]),
                    height=int(profile.height or row["height"]),
                    tolerance=float(
                        self.config.render_parameters.get("coordinate_tolerance", 0.0)
                    ),
                    frame_index=int(row.get("frame_index", 0) or 0),
                )
            except (OSError, ValueError, TypeError, KeyError, IndexError):
                return None

        return sample

    # Input: Callbackresultat und Bundlepfad.
    # Output: Nur fachlich validiertes Resultat als erfolgreich.
    # Ungueltige Erfolgsversprechen werden in unerwartete Fehler umklassifiziert.
    def _validate_callback_result(
        self, case: PlannedCase, result: CaseResult, output: Path
    ) -> CaseResult:
        if result.outcome == CaseOutcome.REJECTED and not _is_proven_rejection(result):
            return replace(
                result,
                outcome=CaseOutcome.UNEXPECTED_FAILED,
                error_code="unproven_rejection",
            )
        if result.outcome != CaseOutcome.SUCCESSFUL:
            return result
        if result.ground_truth_files != result.expected_ground_truth_files:
            return replace(
                result,
                outcome=CaseOutcome.UNEXPECTED_FAILED,
                error_code=(
                    "ground_truth_count_mismatch:"
                    f"expected={result.expected_ground_truth_files},"
                    f"actual={result.ground_truth_files}"
                ),
            )
        validation = validate_run_bundle(
            output,
            workspace=self.workspace,
            source_fingerprint=case.source_fingerprint,
        )
        if not validation.valid:
            return CaseResult(
                case.case_id,
                CaseOutcome.UNEXPECTED_FAILED,
                case.source_fingerprint,
                ArtifactStatus.INCONSISTENT,
                "invalid_bundle",
                validation.ground_truth_files,
                result.expected_ground_truth_files,
                validation.unparseable_artifacts,
                validation.invalid_annotations,
                validation.path_collisions,
                profile=result.profile or case.profile,
            )
        checked = _attach_input_output_status(
            case, result, output, tolerance=self.config.pixel_tolerance
        )
        if checked.input_output_status == "different":
            return replace(
                checked,
                outcome=CaseOutcome.UNEXPECTED_FAILED,
                error_code="input_output_different",
            )
        return checked

    # Input: aktuelle Fallresultate und Blockstatus.
    # Output: Vollstaendige Blocksummary mit globalen offenen IDs.
    def _summary(
        self,
        block: int,
        size: int,
        status: str,
        results: list[CaseResult],
        terminal: set[str],
        in_progress: list[str],
        open_ids: list[str],
        started: float,
        reason: str | None,
        actual_worker_count: int,
    ) -> BlockSummary:
        elapsed = time.perf_counter() - started
        balance = Balance.from_results(
            results, len(terminal) + len(open_ids) + len(in_progress)
        )
        balance.planned = len(terminal) + len(open_ids) + len(in_progress)
        balance.completed_documents = len(terminal)
        balance.in_progress_documents = len(in_progress)
        balance.open_documents = len(open_ids)
        balance.seed, balance.workers, balance.mode = (
            self.config.seed,
            self.config.workers,
            self.config.mode,
        )
        balance.actual_worker_count = (
            actual_worker_count
            if self.config.mode == "parallel" and self.config.workers > 1
            else 1
        )
        (
            balance.block_number,
            balance.block_size,
            balance.block_status,
            balance.abort_reason,
        ) = block, size, status, reason
        balance.elapsed_seconds, balance.throughput_documents_per_second = (
            elapsed,
            len(terminal) / elapsed if elapsed else 0.0,
        )
        _, peak = tracemalloc.get_traced_memory()
        balance.peak_memory_bytes, balance.peak_memory_definition = (
            peak,
            "tracemalloc_process_peak; Worker-Speicher nicht aggregiert",
        )
        balance.worker_execution_status = (
            "single_process_measured"
            if self.config.mode == "sequential" or self.config.workers == 1
            else "thread_pool_measured"
        )
        balance.worker_execution_reason = (
            "Einzelprozess wurde gemessen."
            if self.config.mode == "sequential" or self.config.workers == 1
            else (
                "ThreadPoolExecutor wurde mit der konfigurierten "
                "Workerzahl ausgefuehrt."
            )
        )
        balance.execution_measurement_status = (
            "single_process_measured"
            if self.config.mode == "sequential" or self.config.workers == 1
            else "thread_pool_tracemalloc_measured"
        )
        balance.execution_measurement_reason = (
            (
                "Peak-Memory gilt fuer den Prozess und aggregiert "
                "Python-Allokationen aller Threads."
            )
            if self.config.mode == "parallel" and self.config.workers > 1
            else "Peak-Memory gilt fuer den Einzelprozess."
        )
        balance.output_bytes = sum(result.output_bytes for result in results)
        balance.input_output_differences = sum(
            result.input_output_status == "different" for result in results
        )
        return BlockSummary(
            block,
            size,
            status,
            balance,
            tuple(sorted(terminal)),
            tuple(in_progress),
            tuple(sorted(open_ids)),
            self.config.seed,
            self.config.workers,
            self.config.mode,
            elapsed,
            balance.output_bytes,
            peak,
            reason,
        )

    def _commit_block(self, summary: BlockSummary, results: list[CaseResult]) -> None:
        payload = {
            "summary": asdict(summary),
            "results": [asdict(r) for r in results],
            "completed_case_ids": list(summary.terminal_case_ids),
        }
        checkpoint = {
            "checkpoint_schema_version": self.checkpoint_schema_version,
            "config_fingerprint": self.config.fingerprint(),
            "input_fingerprint": _manifest_fingerprint(self.manifest_path),
            "terminal_case_ids": list(summary.terminal_case_ids),
            "parent_terminal_case_ids": sorted(
                set(summary.terminal_case_ids)
                - {
                    result.case_id
                    for result in results
                    if result.block_number == summary.block_number
                }
            ),
            "completed_case_ids": list(summary.terminal_case_ids),
            "last_completed_block": summary.block_number,
            "block_status": "completed",
            "abort_reason": None,
            "block_number": summary.block_number,
            "block_size": summary.block_size,
            "in_progress_case_ids": list(summary.in_progress_case_ids),
            "open_case_ids": list(summary.open_case_ids),
            "seed": summary.seed,
            "workers": summary.workers,
            "mode": summary.mode,
            "elapsed_seconds": summary.elapsed_seconds,
            "output_bytes": summary.output_bytes,
            "peak_memory_bytes": summary.peak_memory_bytes,
            "balance": asdict(summary.balance),
            "results": [asdict(r) for r in results],
        }
        commits = self.workspace / ".commits"
        commits.mkdir(parents=True, exist_ok=True)
        temporary, published = (
            commits / f".block-{summary.block_number:06d}.tmp",
            commits / f"block-{summary.block_number:06d}",
        )
        if published.exists():
            raise ValueError("Blockcommit existiert bereits.")
        temporary.mkdir()
        _write_atomic(temporary / "block.json", payload)
        _write_atomic(temporary / "checkpoint.json", checkpoint)
        _write_atomic(
            temporary / "case-results.json", {"results": [asdict(r) for r in results]}
        )
        os.replace(temporary, published)
        checkpoint["commit_directory"] = str(published.relative_to(self.workspace))
        _write_atomic(self.checkpoint_path, checkpoint)
        _write_atomic(
            self.workspace / f"block-{summary.block_number:06d}.json", payload
        )
        for result in results:
            _write_atomic(self.results_dir / f"{result.case_id}.json", asdict(result))

    # Input: Kein zusaetzlicher Input; untersucht die Commitablage des Laufs.
    # Output: Keine Rueckgabe; adoptiert genau ein neues vollstaendiges Paket.
    # Ein orphan package wird vor dem Resume als autoritativer Indexstand
    # materialisiert. Unvollstaendige oder mehrdeutige Pakete brechen den Lauf ab.
    def _adopt_orphan_commit(self) -> None:
        commits = self.workspace / ".commits"
        if not commits.is_dir():
            return
        incomplete = [
            path
            for path in commits.glob("*")
            if path.is_dir() and path.name.startswith(".block-")
        ]
        if incomplete:
            raise ValueError("Unvollstaendiges Commit-Paket erkannt.")
        published = sorted(
            path
            for path in commits.glob("block-[0-9][0-9][0-9][0-9][0-9][0-9]")
            if path.is_dir()
        )
        if not published:
            return
        manifest_payload = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        manifest_cases = {
            str(item["case_id"]): str(item["source_fingerprint"])
            for item in manifest_payload.get("cases", [])
            if isinstance(item, dict) and "case_id" in item
        }
        packages: list[tuple[int, dict[str, Any], dict[str, Any]]] = []
        historical_results: dict[str, str] = {}
        for path in published:
            try:
                package_checkpoint = json.loads(
                    (path / "checkpoint.json").read_text(encoding="utf-8")
                )
                package_block = json.loads(
                    (path / "block.json").read_text(encoding="utf-8")
                )
                result_payload = json.loads(
                    (path / "case-results.json").read_text(encoding="utf-8")
                )
                number = int(path.name.rsplit("-", 1)[-1])
            except (
                OSError,
                UnicodeError,
                json.JSONDecodeError,
                TypeError,
                ValueError,
            ) as error:
                raise ValueError(
                    "Commit-Paket ist unvollstaendig oder nicht parsbar."
                ) from error
            if (
                package_checkpoint.get("config_fingerprint")
                != self.config.fingerprint()
            ):
                raise ValueError("Commit-Paket gehoert zu einer anderen Konfiguration.")
            if package_checkpoint.get("input_fingerprint") != _manifest_fingerprint(
                self.manifest_path
            ):
                raise ValueError("Commit-Paket gehoert zu einem anderen Input-Lauf.")
            raw_results = result_payload.get("results")
            if not isinstance(raw_results, list):
                raise ValueError("Commit-Paket ohne CaseResult-Liste.")
            for item in raw_results:
                if not isinstance(item, dict) or "case_id" not in item:
                    continue
                case_id = str(item["case_id"])
                serialized = json.dumps(item, sort_keys=True, default=str)
                if (
                    case_id in historical_results
                    and historical_results[case_id] != serialized
                ):
                    raise ValueError(
                        "Historisches CaseResult wurde in einem Commit veraendert."
                    )
                historical_results.setdefault(case_id, serialized)
            result_ids = [
                str(item.get("case_id"))
                for item in raw_results
                if isinstance(item, dict)
            ]
            checkpoint_ids = {
                str(item) for item in package_checkpoint.get("terminal_case_ids", [])
            }
            if len(result_ids) != len(raw_results) or len(set(result_ids)) != len(
                result_ids
            ):
                raise ValueError(
                    "Commit-Paket enthaelt doppelte oder ungueltige CaseResults."
                )
            if set(result_ids) != checkpoint_ids:
                raise ValueError(
                    "CaseResults und Checkpoint-Faelle unterscheiden sich."
                )
            from .report import (
                compare_balance_fields,
                compare_block_summary_fields,
                reconstruct_case_result_balance,
            )

            reconstructed, result_differences = reconstruct_case_result_balance(
                raw_results,
                len(manifest_cases),
                manifest_cases=manifest_cases,
                block_number=number,
            )
            if result_differences:
                raise ValueError("; ".join(result_differences))
            if reconstructed is None:
                raise ValueError("CaseResults koennen nicht rekonstruiert werden.")
            balance = package_block.get("summary", {}).get("balance", {})
            if package_block.get("summary", {}).get("block_number") != number:
                raise ValueError("Commit-Paket enthaelt eine falsche Blocknummer.")
            summary = package_block.get("summary", {})
            status_differences = compare_block_summary_fields(
                summary, package_checkpoint, label=f"block-{number:06d}"
            )
            if status_differences:
                raise ValueError("; ".join(status_differences))
            balance_differences = compare_balance_fields(
                reconstructed, balance, label=f"block-{number:06d}"
            )
            balance_differences.extend(
                compare_balance_fields(
                    reconstructed,
                    package_checkpoint.get("balance", {}),
                    label=f"checkpoint-{number:06d}",
                )
            )
            if balance_differences:
                raise ValueError("; ".join(balance_differences))
            packages.append((number, package_checkpoint, package_block))
        expected_number = 1
        prior_ids: set[str] = set()
        for number, package_checkpoint, package_block in packages:
            if number != expected_number:
                raise ValueError("Commitpakete bilden keine lueckenlose Blocksequenz.")
            ids = set(
                str(item) for item in package_checkpoint.get("terminal_case_ids", [])
            )
            parent_ids = {
                str(item)
                for item in package_checkpoint.get("parent_terminal_case_ids", [])
            }
            if parent_ids != prior_ids or ids == prior_ids:
                raise ValueError(
                    "Commitpakete enthalten keine konsistente Parent-Kette."
                )
            if not prior_ids <= ids or package_block.get("completed_case_ids") != list(
                package_checkpoint.get("terminal_case_ids", [])
            ):
                raise ValueError(
                    "Commitpakete enthalten keine konsistente kumulative Bilanz."
                )
            prior_ids = ids
            expected_number += 1
        newest = published[-1]
        if self.checkpoint_path.is_file():
            try:
                current = json.loads(self.checkpoint_path.read_text(encoding="utf-8"))
                current_block = int(current.get("last_completed_block", 0))
                newest_block = int(newest.name.rsplit("-", 1)[-1])
                if newest_block <= current_block:
                    return
            except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
                pass
        try:
            checkpoint = json.loads(
                (newest / "checkpoint.json").read_text(encoding="utf-8")
            )
            block = json.loads((newest / "block.json").read_text(encoding="utf-8"))
            result_payload = json.loads(
                (newest / "case-results.json").read_text(encoding="utf-8")
            )
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise ValueError(
                "Veröffentlichtes Commit-Paket ist nicht parsbar."
            ) from error
        if not isinstance(checkpoint, dict) or not isinstance(block, dict):
            raise ValueError("Veröffentlichtes Commit-Paket ist unvollstaendig.")
        latest_ids = checkpoint.get("terminal_case_ids")
        result_ids = [item.get("case_id") for item in result_payload.get("results", [])]
        if latest_ids != block.get("completed_case_ids") or sorted(
            latest_ids or []
        ) != sorted(result_ids):
            raise ValueError("Veröffentlichtes Commit-Paket ist inkonsistent.")
        checkpoint["commit_directory"] = str(newest.relative_to(self.workspace))
        _write_atomic(self.checkpoint_path, checkpoint)

    def _write_interrupted(
        self,
        summary: BlockSummary,
        results: list[CaseResult],
        planned: list[PlannedCase],
    ) -> None:
        from .report import aggregate_profiles, checkpoint_consistency

        previous_commit_directory: str | None = None
        if self.checkpoint_path.is_file():
            try:
                previous_checkpoint = json.loads(
                    self.checkpoint_path.read_text(encoding="utf-8")
                )
                candidate = previous_checkpoint.get("commit_directory")
                if isinstance(candidate, str) and candidate:
                    directory = self.workspace / candidate
                    if previous_checkpoint.get("block_status") == "completed" and all(
                        (directory / name).is_file()
                        for name in (
                            "block.json",
                            "checkpoint.json",
                            "case-results.json",
                        )
                    ):
                        previous_commit_directory = candidate
            except (OSError, UnicodeError, json.JSONDecodeError):
                previous_commit_directory = None

        planned_profiles = [
            case.profile for case in planned if case.profile is not None
        ]
        # Der autoritative Checkpoint bleibt unverändert. Teilresultate des
        # laufenden Blocks sind ausschließlich Beobachtungen des Abbruchs und
        # dürfen beim Resume nicht als abgeschlossen gelten.
        consistency = checkpoint_consistency(self.workspace)
        _write_atomic(
            self.workspace / "run-summary-interrupted.json",
            {
                "report_type": "complete_interrupted_run_report",
                "summary": asdict(summary),
                "run_balance": asdict(summary.balance),
                "block_balances": [
                    item.get("balance", {})
                    for item in consistency.get("block_summaries", [])
                ]
                + [asdict(summary.balance)],
                "checkpoint_consistency": consistency,
                "commit_directory": previous_commit_directory,
                "checkpoint_differences": consistency.get("differences", []),
                "profile_aggregate": aggregate_profiles(
                    [result.profile for result in results if result.profile is not None]
                    + [
                        profile
                        for profile in planned_profiles
                        if profile.case_id not in {result.case_id for result in results}
                    ]
                ),
                "source_fingerprints": sorted(
                    {result.source_fingerprint for result in results}
                ),
                "last_completed_block": summary.block_number - 1,
                "block_status": summary.status,
                "abort_reason": summary.abort_reason,
                "terminal_case_ids": list(summary.terminal_case_ids),
                "in_progress_case_ids": list(summary.in_progress_case_ids),
                "open_case_ids": list(summary.open_case_ids),
                "output_volume_definition": (
                    "Summe der pro Fall erzeugten Dateien vor Evaluation-Cleanup"
                ),
                "peak_memory_definition": summary.balance.peak_memory_definition,
            },
        )

    def _load_checkpoint(self) -> dict[str, Any]:
        payload = json.loads(self.checkpoint_path.read_text(encoding="utf-8"))
        if (
            not isinstance(payload, dict)
            or payload.get("checkpoint_schema_version")
            != self.checkpoint_schema_version
        ):
            raise ValueError("Unbekannte oder unvollstaendige Checkpoint-Version.")
        commit = payload.get("commit_directory")
        if commit:
            directory = self.workspace / str(commit)
            if not all(
                (directory / name).is_file()
                for name in ("block.json", "checkpoint.json", "case-results.json")
            ):
                raise ValueError(
                    "Checkpoint verweist auf einen unvollstaendigen Commit."
                )
            package = json.loads(
                (directory / "checkpoint.json").read_text(encoding="utf-8")
            )
            if package.get("terminal_case_ids") != payload.get("terminal_case_ids"):
                raise ValueError("Commit-Paket und Checkpoint sind inkonsistent.")
            result_payload = json.loads(
                (directory / "case-results.json").read_text(encoding="utf-8")
            )
            result_ids = sorted(
                item.get("case_id") for item in result_payload.get("results", [])
            )
            if result_ids != sorted(payload.get("terminal_case_ids", [])):
                raise ValueError("Commit-Paket und Resultate sind inkonsistent.")
        return cast(dict[str, Any], payload)

    def _results_from_checkpoint(
        self, checkpoint: dict[str, Any] | None
    ) -> list[CaseResult]:
        if not checkpoint:
            return []
        loaded: list[CaseResult] = []
        for raw in checkpoint.get("results", []):
            payload = dict(raw)
            payload["outcome"] = CaseOutcome(str(payload["outcome"]))
            payload["artifact_status"] = ArtifactStatus(
                str(payload.get("artifact_status", ArtifactStatus.MISSING.value))
            )
            profile = payload.get("profile")
            if isinstance(profile, dict):
                profile_payload = dict(profile)
                if "profile_status" in profile_payload:
                    profile_payload["profile_status"] = ProfileStatus(
                        str(profile_payload["profile_status"])
                    )
                for key in (
                    "expected_schema_fields",
                    "present_structured_fields",
                    "used_structured_fields",
                    "missing_expected_fields",
                ):
                    if isinstance(profile_payload.get(key), list):
                        profile_payload[key] = tuple(profile_payload[key])
                payload["profile"] = CaseProfile(**profile_payload)
            loaded.append(CaseResult(**payload))
        return loaded


def _manifest_fingerprint(path: Path) -> str:
    return str(json.loads(path.read_text(encoding="utf-8"))["input_fingerprint"])


# Input: Callbackresultat und geplanter Fall.
# Output: True nur bei nachweisbarer kontrollierter Ablehnung.
def _is_proven_rejection(result: CaseResult) -> bool:
    return has_valid_rejection_evidence(result)


# Input: Erfolgreicher Fall und erzeugtes Bundle.
# Output: Fallresultat mit explizitem Input/Output-Semantikstatus.
def _attach_input_output_status(
    case: PlannedCase,
    result: CaseResult,
    output: Path,
    *,
    tolerance: int = 8,
) -> CaseResult:
    from .semantic_comparison import (
        _annotation_roi,
        _annotation_rois_by_page,
        _resolve_artifact,
        compare_input_output,
    )

    try:
        record_payload = json.loads(
            (output / "ground_truth.json").read_text(encoding="utf-8-sig")
        )
        output_path = _resolve_artifact(record_payload["output_file"], output)
        allowlist = {0x00020010}
        for annotation in record_payload.get("dicom_tag_annotations", []):
            address = str(annotation.get("tag_address", ""))
            if "," in address:
                group, element = address.split(",", 1)
                allowlist.add((int(group, 16) << 16) | int(element, 16))
        roi: tuple[int, int, int, int] | dict[int, tuple[int, int, int, int]] | None = (
            _annotation_rois_by_page(record_payload)
            if case.source.suffix.casefold() == ".pdf"
            else _annotation_roi(record_payload)
        )
        if case.source.suffix.casefold() == ".pdf" and roi is None:
            return replace(
                result,
                input_output_status="unavailable",
                input_output_reason="Seitenbezogene PDF-ROI fehlt",
            )
        status = compare_input_output(
            case.source,
            output_path,
            roi=roi,
            allowlist=allowlist,
            tolerance=tolerance,
        )
        reason = status.get("reason")
        return replace(
            result,
            input_output_status=str(status.get("status")),
            input_output_reason=str(reason) if reason else None,
            input_output_warnings=tuple(
                str(item) for item in status.get("warnings", [])
            ),
            input_output_tolerance=(
                int(status["tolerance"])
                if status.get("tolerance") is not None
                else None
            ),
            input_output_max_absolute_difference=(
                int(status["max_absolute_difference"])
                if status.get("max_absolute_difference") is not None
                else None
            ),
            input_output_mean_absolute_difference=(
                float(status["mean_absolute_difference"])
                if status.get("mean_absolute_difference") is not None
                else None
            ),
            input_output_p99_absolute_difference=(
                float(status["p99_absolute_difference"])
                if status.get("p99_absolute_difference") is not None
                else None
            ),
            input_output_pixels_compared=(
                int(status["pixels_compared"])
                if status.get("pixels_compared") is not None
                else None
            ),
            input_output_pixels_exceeding_tolerance=(
                int(status["pixels_exceeding_tolerance"])
                if status.get("pixels_exceeding_tolerance") is not None
                else None
            ),
            input_output_pixels_exceeding_quality_limit=(
                int(status["pixels_exceeding_quantile_limit"])
                if status.get("pixels_exceeding_quantile_limit") is not None
                else None
            ),
            input_output_large_difference_fraction=(
                float(status["large_difference_fraction"])
                if status.get("large_difference_fraction") is not None
                else None
            ),
            input_output_quality_rule=(
                dict(status["quality_rule"])
                if isinstance(status.get("quality_rule"), dict)
                else {}
            ),
        )
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        ValueError,
    ) as error:
        return replace(
            result, input_output_status="unavailable", input_output_reason=str(error)
        )
