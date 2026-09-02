import shutil
from pathlib import Path
from unittest.mock import patch

import pytest
from tools.thesis_results.verification.case_outcomes import (
    CaseOutcome,
    CaseProfile,
    EvaluationConfig,
    ProfileStatus,
    has_valid_rejection_evidence,
)
from tools.thesis_results.verification.evaluation_callback import run_case
from tools.thesis_results.verification.evaluation_cli import run_evaluation
from tools.thesis_results.verification.evaluation_runner import (
    EvaluationRunner,
    PlannedCase,
)
from tools.thesis_results.verification.semantic_comparison import profile_source

from tests.fixtures.synthetic_documents import write_synthetic_dicom


def test_manifest_is_loadable_and_profiles_local_sources() -> None:
    from tools.thesis_results.verification.evaluation_cli import load_cases

    cases = load_cases(Path("configs/evaluation-manifest.json"))

    assert len(cases) == 8
    assert {case.document_type for case in cases} == {"dcm", "jpg", "pdf"}
    assert all(case.source.is_file() for case in cases)
    assert all(case.profile is not None for case in cases)


def test_callback_rejects_parallel_execution() -> None:
    with pytest.raises(ValueError, match="sequential"):
        run_evaluation(
            Path("configs/evaluation-manifest.json"),
            Path(".qa-parallel-evaluation"),
            run_case,
            workers=2,
            mode="parallel",
        )


def test_unsupported_profile_is_rejected_with_evidence(tmp_path: Path) -> None:
    source = tmp_path / "unsupported.dcm"
    profile = CaseProfile(
        case_id="unsupported",
        source_fingerprint="source",
        document_type="dcm",
        supported=False,
        profile_status=ProfileStatus.COMPLETE,
        profile_reason="DICOM-Repraesentation nicht unterstuetzt",
    )
    case = PlannedCase("unsupported", source, "source", "dcm", profile)

    with patch(
        "tools.thesis_results.verification.evaluation_callback.inject_function"
    ) as inject:
        result = run_case(case, tmp_path / "result")

    inject.assert_not_called()
    assert result.outcome == CaseOutcome.REJECTED
    assert result.rejection_type == "unsupported"
    assert result.rejection_evidence["callback_status"] == "unsupported"


def test_unexpected_api_error_is_not_claimed_as_rejection(tmp_path: Path) -> None:
    source = tmp_path / "source.jpg"
    source.write_bytes(b"fixture")
    case = PlannedCase("case-1", source, "source", "jpg")

    with patch(
        "tools.thesis_results.verification.evaluation_callback.inject_function",
        side_effect=ValueError("invalid input"),
    ):
        result = run_case(case, tmp_path / "result")

    assert result.outcome == CaseOutcome.UNEXPECTED_FAILED
    assert result.rejection_type is None
    assert result.error_code == "ValueError"


def test_existing_case_folder_is_not_overwritten(tmp_path: Path) -> None:
    source = tmp_path / "source.jpg"
    source.write_bytes(b"fixture")
    output = tmp_path / "result"
    output.mkdir()
    sentinel = output / "sentinel.txt"
    sentinel.write_text("keep", encoding="utf-8")
    case = PlannedCase("case-1", source, "source", "jpg")

    result = run_case(case, output)

    assert result.outcome == CaseOutcome.UNEXPECTED_FAILED
    assert result.error_code == "existing_output_directory"
    assert sentinel.read_text(encoding="utf-8") == "keep"


def test_pdf_scope_rejection_contains_valid_evidence() -> None:
    source = Path("DicomData/PDF/Briefmarken.1Stk.17.03.2026_1345.pdf")
    case = PlannedCase("pdf-scope", source, "source", "pdf", expected_rejection=True)

    result = run_case(case, Path(".qa-pdf-rejection-output"))

    assert result.outcome == CaseOutcome.REJECTED
    assert result.rejection_type == "contract_rejection"
    assert result.rejection_evidence["reason_code"] == "contract_violation"
    assert has_valid_rejection_evidence(result)


def test_synthetic_bundle_is_materialized_and_processed_by_runner(
    tmp_path: Path,
) -> None:
    source = write_synthetic_dicom(tmp_path / "source.dcm")
    profile = profile_source(source, "synthetic", used_schema_fields=("patient_id",))
    case = PlannedCase("synthetic", source, profile.source_fingerprint, "dcm", profile)
    workspace = Path(".qa-evaluation-runner")
    shutil.rmtree(workspace, ignore_errors=True)
    try:
        balance = EvaluationRunner(workspace, EvaluationConfig()).run([case], run_case)
        bundle = workspace / "case-results" / "synthetic"

        assert balance.completed_documents == 1
        assert (bundle / "ground_truth.json").is_file()
        assert (bundle / "run_manifest.json").is_file()
        assert not any(
            path.name.startswith(".tmp-")
            for path in (workspace / "case-results").iterdir()
        )
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
