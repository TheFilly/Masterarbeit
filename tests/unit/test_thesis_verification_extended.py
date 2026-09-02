"""Erweiterte deterministische Tests des Evaluations-Harness."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image
from tools.thesis_results.verification.bundle_validation import (
    _document_parseable,
    find_bundle_path_collisions,
)
from tools.thesis_results.verification.case_outcomes import (
    CaseOutcome,
    CaseResult,
    EvaluationConfig,
    ProfileStatus,
    classify_failure,
    has_valid_rejection_evidence,
)
from tools.thesis_results.verification.coordinate_adapter import (
    aggregate_coordinate_cases,
)
from tools.thesis_results.verification.evaluation_cli import load_cases
from tools.thesis_results.verification.evaluation_runner import (
    EvaluationRunner,
    PlannedCase,
)
from tools.thesis_results.verification.report import (
    checkpoint_consistency,
    reconstruct_case_result_balance,
)
from tools.thesis_results.verification.semantic_comparison import (
    compare_dicom_attributes,
    compare_input_output,
    dicom_pixels_equal,
    profile_source,
)

from tests.fixtures.synthetic_documents import write_synthetic_dicom


def _case(case_id: str, source: Path, *, negative: bool = False) -> PlannedCase:
    return PlannedCase(case_id, source, case_id, "jpg", planned_negative=negative)


@pytest.mark.parametrize("error", [OSError("read"), EOFError("eof")])
def test_direct_dicom_pixel_comparison_returns_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    error: Exception,
) -> None:
    import pydicom

    def fail_read(*_args: object, **_kwargs: object) -> object:
        raise error

    monkeypatch.setattr(pydicom, "dcmread", fail_read)
    result = dicom_pixels_equal(tmp_path / "left.dcm", tmp_path / "right.dcm")
    assert result["status"] == "unavailable"
    assert "reason" in result


def test_direct_dicom_attribute_comparison_handles_invalid_dicom(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import pydicom
    from pydicom.errors import InvalidDicomError

    def fail_read(*_args: object, **_kwargs: object) -> object:
        raise InvalidDicomError("invalid")

    monkeypatch.setattr(pydicom, "dcmread", fail_read)
    result = compare_dicom_attributes(tmp_path / "left.dcm", tmp_path / "right.dcm")
    assert result["status"] == "unavailable"
    assert result["reason"] == "invalid"


def test_planned_negative_does_not_hide_internal_exception() -> None:
    assert (
        classify_failure(
            documented_rejection=False,
            planned_negative=True,
            failure_kind="unexpected",
        )
        == CaseOutcome.UNEXPECTED_FAILED
    )


def test_expected_rejection_flag_does_not_classify_callback_exception(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.jpg"
    source.write_bytes(b"fixture")
    case = PlannedCase("a", source, "source", "jpg", expected_rejection=True)

    def callback(_case: PlannedCase, _output: Path) -> CaseResult:
        raise RuntimeError("interner Fehler")

    result = EvaluationRunner(tmp_path / "results", EvaluationConfig()).run(
        [case], callback
    )
    assert result.unexpected_failed == 1
    assert (
        classify_failure(
            documented_rejection=False,
            planned_negative=True,
            failure_kind="unparseable",
        )
        == CaseOutcome.REJECTED
    )


def test_compare_input_output_uses_only_contract_statuses_for_read_errors(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.jpg"
    output = tmp_path / "output.jpg"
    comparison = compare_input_output(source, output)
    assert comparison["status"] == "unavailable"
    assert comparison["status"] in {
        "same",
        "different",
        "unavailable",
        "unsupported",
    }


def test_invalid_dicom_is_unparseable_without_raising(tmp_path: Path) -> None:
    artifact = tmp_path / "broken.dcm"
    artifact.write_bytes(b"not a DICOM file")
    parseable, reason = _document_parseable(artifact)
    assert not parseable
    assert reason == "Ausgabedokument ist nicht parsbar"


def test_invalid_dicom_profile_is_non_parseable_without_raising(tmp_path: Path) -> None:
    artifact = tmp_path / "broken.dcm"
    artifact.write_bytes(b"not a DICOM file")

    profile = profile_source(artifact, "broken")

    assert profile.profile_status == ProfileStatus.NON_PARSEABLE
    assert profile.profile_reason == "Quelle konnte nicht geparst werden"


def test_load_cases_keeps_invalid_dicom_as_non_parseable_case(tmp_path: Path) -> None:
    source = tmp_path / "broken.dcm"
    source.write_bytes(b"invalid source")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({"cases": [{"case_id": "broken", "source": "broken.dcm"}]}),
        encoding="utf-8",
    )

    cases = load_cases(manifest)

    assert len(cases) == 1
    assert cases[0].profile is not None
    assert cases[0].profile.profile_status == ProfileStatus.NON_PARSEABLE


def test_invalid_dicom_input_output_is_unavailable_without_raising(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.dcm"
    output = tmp_path / "output.dcm"
    source.write_bytes(b"invalid source")
    output.write_bytes(b"invalid output")

    comparison = compare_input_output(source, output)

    assert comparison["status"] == "unavailable"
    assert comparison["reason"]


def test_runner_bilanzes_non_parseable_dicom_as_unexpected_failure(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.dcm"
    source.write_bytes(b"invalid source")
    case = PlannedCase(
        "broken",
        source,
        "source",
        "dcm",
        profile_source(source, "broken"),
    )

    def callback(_case: PlannedCase, _output: Path) -> CaseResult:
        raise AssertionError("Callback darf fuer nicht parsbare DICOMs nicht laufen")

    balance = EvaluationRunner(tmp_path / "results", EvaluationConfig()).run(
        [case], callback
    )

    assert balance.unexpected_failed == 1
    assert balance.unparseable_artifacts == 1


def test_checkpoint_is_commit_boundary_after_projection_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.jpg"
    source.write_bytes(b"fixture")
    workspace = tmp_path / "results"
    cases = [_case("a", source), _case("b", source)]
    calls: list[str] = []
    original = __import__(
        "tools.thesis_results.verification.evaluation_runner",
        fromlist=["_write_atomic"],
    )._write_atomic
    failed = True

    def flaky(path: Path, payload: object) -> None:
        nonlocal failed
        if failed and path.name.startswith("block-"):
            failed = False
            raise OSError("simulierter Crash nach Checkpoint")
        original(path, payload)

    monkeypatch.setattr(
        "tools.thesis_results.verification.evaluation_runner._write_atomic", flaky
    )

    def callback(case: PlannedCase, _output: Path) -> CaseResult:
        calls.append(case.case_id)
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

    with pytest.raises(OSError, match="simulierter Crash"):
        EvaluationRunner(workspace, EvaluationConfig(block_size=2)).run(cases, callback)
    assert json.loads((workspace / "checkpoint.json").read_text())[
        "completed_case_ids"
    ] == ["a", "b"]
    calls.clear()
    assert (
        EvaluationRunner(workspace, EvaluationConfig(block_size=2))
        .run(cases, callback, resume=True)
        .rejected
        == 2
    )
    assert calls == []


def test_interrupted_run_keeps_checkpoint_authoritative(tmp_path: Path) -> None:
    source = tmp_path / "source.jpg"
    source.write_bytes(b"fixture")
    runner = EvaluationRunner(tmp_path / "results", EvaluationConfig(block_size=2))
    cases = [_case("a", source), _case("b", source)]
    count = 0

    def callback(case: PlannedCase, _output: Path) -> CaseResult:
        nonlocal count
        count += 1
        if count == 2:
            raise KeyboardInterrupt()
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

    with pytest.raises(KeyboardInterrupt):
        runner.run(cases, callback)
    assert not runner.checkpoint_path.exists()
    report = json.loads((runner.workspace / "run-summary-interrupted.json").read_text())
    assert report["block_status"] == "interrupted"
    assert report["in_progress_case_ids"] == ["b"]
    assert report["open_case_ids"] == []


def test_profile_source_reports_dimensions_and_reuse(tmp_path: Path) -> None:
    image_path = tmp_path / "source.jpg"
    Image.new("RGB", (32, 16), (0, 0, 0)).save(image_path)
    profile = profile_source(
        image_path,
        "case-a",
        placement_mode="free",
        rotation_degrees=90,
        font_or_renderer="arial",
    )
    assert profile.width == 32
    assert profile.height == 16
    assert profile.placement_mode == "free"
    assert profile.rotation_degrees == 90
    assert profile.profile_status.value == "complete"


def test_input_output_raster_detects_change_outside_roi(tmp_path: Path) -> None:
    source = tmp_path / "source.jpg"
    output = tmp_path / "output.jpg"
    image = Image.new("RGB", (16, 16), (255, 255, 255))
    image.save(source)
    changed = image.copy()
    changed.putpixel((15, 15), (0, 0, 0))
    changed.putpixel((14, 15), (0, 0, 0))
    changed.save(output)
    comparison = compare_input_output(source, output, roi=(0, 0, 4, 4))
    assert comparison["status"] == "different"


def test_input_output_raster_uses_same_for_unchanged_input(tmp_path: Path) -> None:
    source = tmp_path / "source.jpg"
    output = tmp_path / "output.jpg"
    image = Image.new("RGB", (16, 16), (255, 255, 255))
    image.save(source)
    image.save(output)

    comparison = compare_input_output(source, output)

    assert comparison["status"] == "same"


def test_input_output_raster_accepts_reencoding_with_warning_within_tolerance(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.png"
    output = tmp_path / "output.png"
    Image.new("RGB", (16, 16), (100, 100, 100)).save(source)
    changed = Image.open(source).copy()
    changed.putpixel((15, 15), (108, 100, 100))
    changed.save(output)

    comparison = compare_input_output(source, output, roi=(0, 0, 4, 4), tolerance=8)

    assert comparison["status"] == "same_with_warnings"
    assert comparison["warnings"]
    assert comparison["max_absolute_difference"] == 8
    assert comparison["pixels_exceeding_tolerance"] == 0


def test_input_output_raster_rejects_difference_above_tolerance(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    output = tmp_path / "output.png"
    image = Image.new("RGB", (16, 16), (100, 100, 100))
    image.save(source)
    changed = image.copy()
    for x in range(8):
        for y in range(8):
            changed.putpixel((x, y), (200, 100, 100))
    changed.save(output)

    comparison = compare_input_output(source, output, roi=(0, 0, 4, 4), tolerance=8)

    assert comparison["status"] == "different"
    assert comparison["pixels_exceeding_tolerance"] == 48
    assert comparison["p99_absolute_difference"] > 32


def test_rgb_dicom_roi_masks_rows_columns_and_samples_without_mocking(
    tmp_path: Path,
) -> None:
    source = write_synthetic_dicom(tmp_path / "source.dcm")
    output = tmp_path / "output.dcm"
    import pydicom

    dataset = pydicom.dcmread(source)
    pixels = dataset.pixel_array.copy()
    pixels[0, 0, :] = 255
    dataset.PixelData = pixels.tobytes()
    dataset.save_as(output, enforce_file_format=True)

    comparison = dicom_pixels_equal(source, output, roi=(0, 0, 1, 1), tolerance=8)

    assert comparison["status"] == "same"
    assert comparison["max_absolute_difference"] == 0
    assert comparison["pixels_compared"] == (256 * 256 - 1) * 3


def test_dicom_color_conversion_is_a_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import pydicom
    from tools.thesis_results.verification import semantic_comparison

    source = tmp_path / "source.dcm"
    output = tmp_path / "output.dcm"
    source_dataset = pydicom.Dataset()
    output_dataset = pydicom.Dataset()
    for dataset in (source_dataset, output_dataset):
        dataset.Rows = 2
        dataset.Columns = 2
        dataset.SamplesPerPixel = 3
        dataset.PhotometricInterpretation = "YBR_FULL_422"
        dataset.PixelRepresentation = 0
        dataset.BitsAllocated = 8
        dataset.BitsStored = 8
        dataset.HighBit = 7
    output_dataset.PhotometricInterpretation = "RGB"

    def read_dicom(path: Path, **_kwargs: object) -> pydicom.Dataset:
        return source_dataset if Path(path) == source else output_dataset

    monkeypatch.setattr(pydicom, "dcmread", read_dicom)
    monkeypatch.setattr(
        semantic_comparison,
        "dicom_pixels_equal",
        lambda *_args, **_kwargs: {
            "status": "same",
            "max_absolute_difference": 0,
            "mean_absolute_difference": 0.0,
            "pixels_compared": 6,
            "pixels_exceeding_tolerance": 0,
        },
    )

    comparison = compare_input_output(source, output, tolerance=8)

    assert comparison["status"] == "same_with_warnings"
    assert any("YBR_FULL_422 -> RGB" in item for item in comparison["warnings"])


def test_profile_source_recognises_pdf(tmp_path: Path) -> None:
    reportlab = pytest.importorskip("reportlab.pdfgen.canvas")
    path = tmp_path / "source.pdf"
    canvas = reportlab.Canvas(str(path))
    canvas.drawString(10, 10, "fixture")
    canvas.save()
    profile = profile_source(path, "case-pdf")
    assert profile.document_type == "pdf"
    assert profile.profile_status.value == "complete"


def test_resume_adopts_published_package_after_outer_checkpoint_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.jpg"
    source.write_bytes(b"fixture")
    workspace = tmp_path / "results"
    cases = [_case("a", source)]
    calls: list[str] = []
    module = __import__(
        "tools.thesis_results.verification.evaluation_runner",
        fromlist=["_write_atomic"],
    )
    original = module._write_atomic
    crashed = True

    def crash_after_publish(path: Path, payload: object) -> None:
        nonlocal crashed
        if crashed and path == workspace / "checkpoint.json":
            crashed = False
            raise OSError("Crash nach Package-Publish")
        original(path, payload)

    monkeypatch.setattr(module, "_write_atomic", crash_after_publish)

    def callback(case: PlannedCase, _output: Path) -> CaseResult:
        calls.append(case.case_id)
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

    with pytest.raises(OSError, match="Package-Publish"):
        EvaluationRunner(workspace, EvaluationConfig()).run(cases, callback)
    calls.clear()
    result = EvaluationRunner(workspace, EvaluationConfig()).run(
        cases, callback, resume=True
    )
    assert result.rejected == 1
    assert calls == []


def test_incomplete_published_package_is_rejected_on_resume(tmp_path: Path) -> None:
    workspace = tmp_path / "results"
    commit = workspace / ".commits" / "block-000001"
    commit.mkdir(parents=True)
    (commit / "checkpoint.json").write_text("{}", encoding="utf-8")
    checkpoint = {
        "checkpoint_schema_version": "3.0",
        "config_fingerprint": EvaluationConfig().fingerprint(),
    }
    workspace.mkdir(exist_ok=True)
    (workspace / "checkpoint.json").write_text(json.dumps(checkpoint), encoding="utf-8")
    runner = EvaluationRunner(workspace, EvaluationConfig())
    with pytest.raises(ValueError, match="Commit-Paket"):
        runner.run(
            [], lambda _case, _output: pytest.fail("nicht erwartet"), resume=True
        )


def test_coordinate_aggregation_uses_case_block_number(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ground_truth = tmp_path / "ground_truth.json"
    ground_truth.write_text(
        json.dumps(
            {
                "run_id": "r",
                "document_type": "jpg",
                "box_annotations": [{"label": "x", "corners": [{"x": 1, "y": 1}] * 4}],
            }
        ),
        encoding="utf-8",
    )
    profile = __import__(
        "tools.thesis_results.verification.case_outcomes",
        fromlist=["CaseProfile"],
    ).CaseProfile("a", "source", width=10, height=10)
    result = CaseResult("a", CaseOutcome.REJECTED, "source", block_number=7)
    aggregate = aggregate_coordinate_cases([(ground_truth, profile, result)])
    assert "7" in aggregate["blocks"]


def test_global_collision_scans_all_record_references(tmp_path: Path) -> None:
    # Ungueltige Minimalrecords werden sicher uebersprungen.
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (first / "ground_truth.json").write_text("{}", encoding="utf-8")
    (second / "ground_truth.json").write_text("{}", encoding="utf-8")
    assert find_bundle_path_collisions([first, second]) == ()


def test_checkpoint_reconstruction_detects_tampered_detail_fields() -> None:
    raw = [
        {
            "case_id": "a",
            "outcome": "rejected",
            "source_fingerprint": "source",
            "artifact_status": "missing",
            "error_code": "contract_rejection",
            "rejection_type": "contract_rejection",
            "rejection_reason": "Fixture-Vertrag nicht erfuellt",
            "rejection_evidence": {
                "callback_status": "contract_rejection",
                "reason_code": "contract_violation",
                "reason": "Fixture-Vertrag nicht erfuellt",
            },
            "output_bytes": 999,
            "block_number": 1,
        }
    ]
    balance, differences = reconstruct_case_result_balance(
        raw, 1, manifest_cases={"a": "source"}, block_number=1
    )
    assert balance is not None
    assert balance.output_bytes == 999
    assert differences == []

    raw[0]["output_bytes"] = -1
    balance, differences = reconstruct_case_result_balance(
        raw, 1, manifest_cases={"a": "source"}, block_number=1
    )
    assert balance is not None
    assert any("Negative CaseResult-Metrik" in item for item in differences)


def test_checkpoint_reconstruction_rejects_missing_rejection_reason() -> None:
    balance, differences = reconstruct_case_result_balance(
        [
            {
                "case_id": "a",
                "outcome": "rejected",
                "source_fingerprint": "source",
                "artifact_status": "missing",
                "block_number": 1,
            }
        ],
        1,
        manifest_cases={"a": "source"},
        block_number=1,
    )
    assert balance is not None
    assert any("Ablehnung ohne validierte Evidenz" in item for item in differences)


def test_unverified_rejection_reason_is_not_controlled() -> None:
    from tools.thesis_results.verification.case_outcomes import ArtifactStatus
    from tools.thesis_results.verification.evaluation_runner import _is_proven_rejection

    assert not _is_proven_rejection(
        CaseResult(
            "a", CaseOutcome.REJECTED, "source", ArtifactStatus.VALID, "unsupported"
        )
    )


def test_rejection_flags_alone_are_not_evidence() -> None:
    result = CaseResult(
        "case-a",
        CaseOutcome.REJECTED,
        "fingerprint",
        rejection_type="contract_rejection",
        rejection_reason="Fixture-Vertrag nicht erfuellt",
        rejection_evidence={
            "validated": True,
            "contract_validated": True,
            "error_code": "contract_rejection",
        },
    )
    assert not has_valid_rejection_evidence(result)


def test_declared_output_audit_counts_nested_and_reports_unexpected(
    tmp_path: Path,
) -> None:
    from tools.thesis_results.verification.evaluation_runner import (
        _declared_output_audit,
    )

    (tmp_path / "nested").mkdir()
    (tmp_path / "ground_truth.json").write_text(
        json.dumps({"output_file": "nested/output.jpg"}), encoding="utf-8"
    )
    (tmp_path / "run_manifest.json").write_text("{}", encoding="utf-8")
    (tmp_path / "nested" / "output.jpg").write_bytes(b"123")
    (tmp_path / "unexpected.bin").write_bytes(b"4567")
    size, unexpected = _declared_output_audit(tmp_path)
    expected = (
        (tmp_path / "ground_truth.json").stat().st_size
        + (tmp_path / "run_manifest.json").stat().st_size
        + 3
    )
    assert size == expected
    assert "unexpected.bin" in unexpected


def test_coordinate_report_marks_missing_pixel_measurement() -> None:
    from tools.thesis_results.verification.coordinate_adapter import (
        aggregate_coordinate_cases,
    )

    assert (
        aggregate_coordinate_cases([], pixel_sample_rate=0)["pixel_metric_status"]
        == "not_executed"
    )


def test_coordinate_report_executes_configured_pixel_sampler(tmp_path: Path) -> None:
    from tools.thesis_results.verification.case_outcomes import CaseProfile

    ground_truth = tmp_path / "ground_truth.json"
    ground_truth.write_text(
        json.dumps(
            {
                "run_id": "r",
                "box_annotations": [{"corners": [{"x": 1, "y": 1}] * 4, "label": "x"}],
            }
        ),
        encoding="utf-8",
    )
    calls: list[int] = []

    def sampler(
        _path: Path, row: dict[str, object], _profile: CaseProfile
    ) -> dict[str, object]:
        calls.append(int(row["annotation_index"]))
        return {
            "center_error_px": 0.0,
            "iou": 1.0,
            "within_tolerance": True,
            "pixel_metric_status": "measured",
        }

    profile = CaseProfile("case", "source", width=10, height=10)
    metrics = aggregate_coordinate_cases(
        [(ground_truth, profile)], pixel_sampler=sampler, pixel_sample_rate=1.0
    )
    assert calls == [0]
    assert metrics["pixel_metric_status"] == "measured"
    assert metrics["total"]["tolerance_unknown"] == 0


def test_parallel_mode_uses_thread_pool_and_reports_native_memory_limit(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.jpg"
    source.write_bytes(b"fixture")
    result = EvaluationRunner(
        tmp_path / "results", EvaluationConfig(mode="parallel", workers=2)
    ).run(
        [_case("a", source)],
        lambda case, _output: CaseResult(
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
        ),
    )
    assert result.worker_execution_status == "thread_pool_measured"
    assert result.execution_measurement_status == "thread_pool_tracemalloc_measured"
    assert "Worker-Speicher nicht aggregiert" in result.peak_memory_definition
    assert "Python-Allokationen aller Threads" in result.execution_measurement_reason


def test_interrupted_checkpoint_preserves_previous_commit_reference(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.jpg"
    source.write_bytes(b"fixture")
    workspace = tmp_path / "results"
    cases = [_case("a", source), _case("b", source)]

    def callback(case: PlannedCase, _output: Path) -> CaseResult:
        if case.case_id == "b":
            raise KeyboardInterrupt("abbruch")
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

    runner = EvaluationRunner(workspace, EvaluationConfig(block_size=1))
    with pytest.raises(KeyboardInterrupt, match="abbruch"):
        runner.run(cases, callback)
    checkpoint = json.loads(runner.checkpoint_path.read_text(encoding="utf-8"))
    assert Path(checkpoint["commit_directory"]) == Path(".commits", "block-000001")
    assert checkpoint_consistency(workspace)["status"] == "consistent"


def test_checkpoint_consistency_detects_tampered_block_status_field(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.jpg"
    source.write_bytes(b"fixture")
    workspace = tmp_path / "results"

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

    EvaluationRunner(workspace, EvaluationConfig(block_size=1)).run(
        [_case("a", source)], callback
    )
    block = workspace / ".commits" / "block-000001" / "block.json"
    payload = json.loads(block.read_text(encoding="utf-8"))
    payload["summary"]["mode"] = "parallel"
    block.write_text(json.dumps(payload), encoding="utf-8")
    consistency = checkpoint_consistency(workspace)
    assert consistency["status"] == "inconsistent"
    assert any("mode" in item for item in consistency["differences"])


def test_pdf_comparison_reports_unavailable_without_renderer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tools.thesis_results.verification import semantic_comparison

    source = tmp_path / "source.pdf"
    output = tmp_path / "output.pdf"
    source.write_bytes(b"pdf")
    output.write_bytes(b"pdf")
    monkeypatch.setattr(semantic_comparison.shutil, "which", lambda _name: None)
    comparison = compare_input_output(source, output)
    assert comparison == {
        "status": "unavailable",
        "reason": "pdftoppm nicht verfuegbar",
    }


def test_bundle_counts_unparseable_generated_document_separately(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace

    import tools.thesis_results.verification.bundle_validation as validation_module

    generated = tmp_path / "generated.unknown"
    generated.write_bytes(b"not a supported document")
    (tmp_path / "ground_truth.json").write_text("{}", encoding="utf-8")
    record = SimpleNamespace(
        record_type="run",
        schema_version="0.2.0-prototype",
        identity_id="identity",
        run_id="run",
        dicom_tag_annotations=[],
        span_annotations=[],
        box_annotations=[],
        model_dump=lambda mode="json": {"record_type": "run"},
    )
    monkeypatch.setattr(validation_module, "load_run_record", lambda _path: record)
    monkeypatch.setattr(
        validation_module,
        "_record_paths",
        lambda _record: [(generated, True)],
    )
    validation = validation_module.validate_run_bundle(tmp_path)
    assert validation.physical_ground_truth_files == 1
    assert validation.ground_truth_files == 1
    assert validation.unparseable_artifacts == 1
    assert validation.unavailable_artifacts == 0


def test_full_pdf_bundle_compare_passes_page_indexed_rois(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tools.thesis_results.verification import semantic_comparison

    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    payload = {
        "output_file": "document.pdf",
        "box_annotations": [
            {
                "frame_index": 0,
                "corners": [{"x": 1, "y": 2}] * 4,
            },
            {
                "frame_index": 1,
                "corners": [{"x": 3, "y": 4}] * 4,
            },
        ],
    }
    for bundle in (left, right):
        (bundle / "ground_truth.json").write_text(json.dumps(payload), encoding="utf-8")
        (bundle / "document.pdf").write_bytes(b"pdf")
    captured: list[object] = []

    def fake_compare(*_args: object, **kwargs: object) -> bool:
        captured.append(kwargs["roi"])
        return True

    monkeypatch.setattr(semantic_comparison, "_compare_pdf_outputs", fake_compare)
    assert semantic_comparison._compare_bundle_pair(left, right, 0)
    assert captured == [{0: (1, 2, 2, 3), 1: (3, 4, 4, 5)}]
