"""Deterministische Regressionen fuer die qualitative Thesis-Evaluation."""

from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
import tools.thesis_results.verification.evaluation_runner as evaluation_runner_module
from tools.thesis_results.verification.bundle_validation import validate_run_bundle
from tools.thesis_results.verification.case_outcomes import (
    ArtifactStatus,
    Balance,
    CaseOutcome,
    CaseResult,
    EvaluationConfig,
    classify_failure,
)
from tools.thesis_results.verification.evaluation_runner import (
    EvaluationRunner,
    PlannedCase,
)
from tools.thesis_results.verification.report import aggregate_profiles
from tools.thesis_results.verification.semantic_comparison import normalized_json_equal


def _case(case_id: str, source: Path) -> PlannedCase:
    return PlannedCase(case_id, source, case_id, "jpg")


def test_balance_requires_complete_terminal_classification() -> None:
    result = CaseResult("a", CaseOutcome.REJECTED, "source")
    balance = Balance.from_results([result], planned=1)
    balance.assert_complete()
    incomplete = Balance.from_results([], planned=1)
    with pytest.raises(ValueError, match="nicht vollstaendig"):
        incomplete.assert_complete()


def test_failure_classification_requires_explicit_negative_case() -> None:
    assert (
        classify_failure(documented_rejection=True, planned_negative=False)
        == CaseOutcome.REJECTED
    )
    assert (
        classify_failure(documented_rejection=False, planned_negative=True)
        == CaseOutcome.REJECTED
    )
    assert (
        classify_failure(documented_rejection=False, planned_negative=False)
        == CaseOutcome.UNEXPECTED_FAILED
    )


def test_runner_writes_manifest_checkpoint_and_resumes(tmp_path: Path) -> None:
    source = tmp_path / "input.jpg"
    source.write_bytes(b"fixture")
    cases = [_case("a", source), _case("b", source)]
    runner = EvaluationRunner(
        tmp_path / "thesis-results", EvaluationConfig(block_size=1)
    )
    calls: list[str] = []

    def callback(case: PlannedCase, output: Path) -> CaseResult:
        calls.append(case.case_id)
        output.mkdir(parents=True, exist_ok=True)
        return CaseResult(
            case.case_id,
            CaseOutcome.REJECTED,
            case.source_fingerprint,
            error_code="contract_rejection",
            rejection_type="contract_rejection",
            rejection_reason="Fixture-Vertrag nicht erfuellt",
            rejection_evidence={
                "callback_status": "contract_rejection",
                "reason_code": "contract_violation",
                "reason": "Fixture-Vertrag nicht erfuellt",
            },
        )

    assert runner.run(cases, callback).rejected == 2
    assert calls == ["a", "b"]
    assert (runner.workspace / "input-manifest.json").is_file()
    assert (runner.workspace / "checkpoint.json").is_file()

    calls.clear()
    assert runner.run(cases, callback, resume=True).rejected == 2
    assert calls == []


def test_runner_rejects_changed_configuration(tmp_path: Path) -> None:
    source = tmp_path / "input.jpg"
    source.write_bytes(b"fixture")
    cases = [_case("a", source)]
    workspace = tmp_path / "results"
    EvaluationRunner(workspace, EvaluationConfig(block_size=1)).prepare(cases)
    (workspace / "checkpoint.json").write_text(
        json.dumps({"config_fingerprint": "different"}), encoding="utf-8"
    )
    runner = EvaluationRunner(workspace, EvaluationConfig(block_size=1))
    with pytest.raises(ValueError, match="Konfiguration"):
        runner.run(
            cases, lambda _case, _output: pytest.fail("nicht erwartet"), resume=True
        )


def test_bundle_validator_ignores_newline_difference(tmp_path: Path) -> None:
    payload = {"schema_version": "0.2.0-prototype", "record_type": "run"}
    gt = tmp_path / "ground_truth.json"
    manifest = tmp_path / "run_manifest.json"
    gt.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    validation = validate_run_bundle(tmp_path)
    assert not validation.valid
    assert any(issue.code == "invalid_run_record" for issue in validation.issues)


def test_profile_aggregation_marks_fixture_reuse() -> None:
    from tools.thesis_results.verification.case_outcomes import CaseProfile

    profiles = [CaseProfile("a", "same"), CaseProfile("b", "same")]
    aggregate = aggregate_profiles(profiles)
    assert aggregate["unique_sources"] == 1
    assert aggregate["evaluation_kind"] == "fixture_reuse_endurance"
    assert aggregate["reuse_factor"] == 2.0


def test_semantic_json_comparison_ignores_formatting(tmp_path: Path) -> None:
    left = tmp_path / "left.json"
    right = tmp_path / "right.json"
    left.write_text('{"a": 1}\n', encoding="utf-8")
    right.write_text('{\n  "a": 1\n}', encoding="utf-8")
    assert normalized_json_equal(left, right)


def test_success_with_missing_ground_truth_becomes_unexpected_failure(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.jpg"
    source.write_bytes(b"fixture")
    runner = EvaluationRunner(tmp_path / "results", EvaluationConfig())
    case = _case("a", source)

    def callback(_case: PlannedCase, _output: Path) -> CaseResult:
        return CaseResult(
            "a",
            CaseOutcome.SUCCESSFUL,
            "a",
            ArtifactStatus.VALID,
            ground_truth_files=0,
        )

    balance = runner.run([case], callback)
    assert balance.successful == 0
    assert balance.rejected == 0
    assert balance.unexpected_failed == 1
    assert balance.planned == 1
    assert balance.ground_truth_missing == 1
    committed = json.loads(
        (
            runner.workspace / ".commits" / "block-000001" / "case-results.json"
        ).read_text(encoding="utf-8")
    )
    assert "ground_truth_count_mismatch" in committed["results"][0]["error_code"]


def test_ground_truth_mismatch_does_not_abort_following_block_or_resume(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.jpg"
    source.write_bytes(b"fixture")
    workspace = tmp_path / "results"
    cases = [_case("bad", source), _case("later", source)]
    calls: list[str] = []
    fail_later = True

    def callback(case: PlannedCase, output: Path) -> CaseResult:
        nonlocal fail_later
        calls.append(case.case_id)
        if case.case_id == "bad":
            return CaseResult(
                case.case_id,
                CaseOutcome.SUCCESSFUL,
                case.source_fingerprint,
                ArtifactStatus.VALID,
                ground_truth_files=0,
            )
        if fail_later:
            fail_later = False
            raise KeyboardInterrupt("kontrollierter Abbruch")
        return CaseResult(
            case.case_id,
            CaseOutcome.REJECTED,
            case.source_fingerprint,
            error_code="contract_rejection",
            rejection_type="contract_rejection",
            rejection_reason="Fixture-Vertrag nicht erfuellt",
            rejection_evidence={
                "callback_status": "contract_rejection",
                "reason_code": "contract_violation",
                "reason": "Fixture-Vertrag nicht erfuellt",
            },
        )

    with pytest.raises(KeyboardInterrupt, match="kontrollierter Abbruch"):
        EvaluationRunner(workspace, EvaluationConfig(block_size=1)).run(
            cases, callback
        )
    interrupted = json.loads(
        (workspace / "run-summary-interrupted.json").read_text(encoding="utf-8")
    )
    assert interrupted["in_progress_case_ids"] == ["later"]
    assert interrupted["open_case_ids"] == []
    assert interrupted["terminal_case_ids"] == ["bad"]

    result = EvaluationRunner(workspace, EvaluationConfig(block_size=1)).run(
        cases, callback, resume=True
    )
    assert result.unexpected_failed == 1
    assert result.rejected == 1
    assert result.planned == (
        result.successful + result.rejected + result.unexpected_failed
    )
    assert calls == ["bad", "later", "later"]


def test_parallel_runner_executes_workers_and_preserves_case_order(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.jpg"
    source.write_bytes(b"fixture")
    cases = [_case(name, source) for name in ("c", "a", "b")]
    runner = EvaluationRunner(
        tmp_path / "results",
        EvaluationConfig(block_size=3, workers=2, mode="parallel"),
    )
    barrier = threading.Barrier(2)
    active = 0
    maximum_active = 0
    lock = threading.Lock()

    def callback(case: PlannedCase, output: Path) -> CaseResult:
        nonlocal active, maximum_active
        with lock:
            active += 1
            maximum_active = max(maximum_active, active)
        if case.case_id in {"c", "a"}:
            barrier.wait(timeout=5)
        with lock:
            active -= 1
        return CaseResult(
            case.case_id,
            CaseOutcome.REJECTED,
            case.source_fingerprint,
            error_code="contract_rejection",
            rejection_type="contract_rejection",
            rejection_reason="Fixture-Vertrag nicht erfuellt",
            rejection_evidence={
                "callback_status": "contract_rejection",
                "reason_code": "contract_violation",
                "reason": "Fixture-Vertrag nicht erfuellt",
            },
        )

    balance = runner.run(cases, callback)
    assert balance.rejected == 3
    assert balance.worker_execution_status == "thread_pool_measured"
    assert balance.actual_worker_count == 2
    assert balance.execution_measurement_status == "thread_pool_tracemalloc_measured"
    assert maximum_active >= 2
    checkpoint = json.loads(
        (runner.workspace / "checkpoint.json").read_text(encoding="utf-8")
    )
    assert checkpoint["terminal_case_ids"] == ["a", "b", "c"]


def test_actual_worker_count_uses_started_threads_not_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.jpg"
    source.write_bytes(b"fixture")
    cases = [_case(name, source) for name in ("a", "b", "c", "d")]

    def single_thread_pool(*args: object, **kwargs: object) -> ThreadPoolExecutor:
        del args, kwargs
        return ThreadPoolExecutor(max_workers=1)

    monkeypatch.setattr(
        evaluation_runner_module,
        "ThreadPoolExecutor",
        single_thread_pool,
    )
    runner = EvaluationRunner(
        tmp_path / "results",
        EvaluationConfig(block_size=4, workers=4, mode="parallel"),
    )

    def callback(case: PlannedCase, _output: Path) -> CaseResult:
        return CaseResult(
            case.case_id,
            CaseOutcome.REJECTED,
            case.source_fingerprint,
            error_code="contract_rejection",
            rejection_type="contract_rejection",
            rejection_reason="Fixture-Vertrag nicht erfuellt",
            rejection_evidence={
                "callback_status": "contract_rejection",
                "reason_code": "contract_violation",
                "reason": "Fixture-Vertrag nicht erfuellt",
            },
        )

    balance = runner.run(cases, callback)
    assert balance.actual_worker_count == 1
    assert balance.actual_worker_count < balance.workers
    assert balance.worker_execution_status == "thread_pool_measured"


def test_parallel_abort_persists_started_and_unstarted_cases_separately(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.jpg"
    source.write_bytes(b"fixture")
    workspace = tmp_path / "results"
    cases = [_case(name, source) for name in ("a", "b", "c", "d")]
    started: list[str] = []
    b_started = threading.Event()
    abort_seen = threading.Event()
    release_running = threading.Event()

    def callback(case: PlannedCase, _output: Path) -> CaseResult:
        started.append(case.case_id)
        if case.case_id == "a":
            b_started.wait(timeout=5)
            abort_seen.set()
            raise KeyboardInterrupt("abbruch")
        if case.case_id == "b":
            b_started.set()
            abort_seen.wait(timeout=5)
            release_running.wait(timeout=5)
        return CaseResult(
            case.case_id,
            CaseOutcome.REJECTED,
            case.source_fingerprint,
            error_code="contract_rejection",
            rejection_type="contract_rejection",
            rejection_reason="Fixture-Vertrag nicht erfuellt",
            rejection_evidence={
                "callback_status": "contract_rejection",
                "reason_code": "contract_violation",
                "reason": "Fixture-Vertrag nicht erfuellt",
            },
        )

    runner = EvaluationRunner(
        workspace, EvaluationConfig(block_size=4, workers=2, mode="parallel")
    )
    try:
        with pytest.raises(KeyboardInterrupt, match="abbruch"):
            runner.run(cases, callback)
        report = json.loads(
            (workspace / "run-summary-interrupted.json").read_text(encoding="utf-8")
        )
        assert set(started) == {"a", "b"}
        assert len(started) == 2
        assert report["in_progress_case_ids"] == ["a", "b"]
        assert report["open_case_ids"] == ["c", "d"]
        assert report["terminal_case_ids"] == []
    finally:
        release_running.set()
