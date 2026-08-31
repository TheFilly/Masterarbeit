from __future__ import annotations

import argparse
from pathlib import Path
from typing import cast
from unittest.mock import patch

import pytest
from tools.thesis_results.pc_runtime_suite import (
    DEFAULT_COUNTS,
    DEFAULT_WORKERS,
    build_plan,
    build_scalability_command,
    create_output_root,
    parse_counts,
    parse_workers,
    run_suite,
)


def test_default_plan_has_six_scaling_and_five_parallel_experiments() -> None:
    plan = build_plan(Path("input"), Path("run"), skip_pdf=True)

    assert tuple(int(item.name.split("-")[1]) for item in plan[:6]) == DEFAULT_COUNTS
    assert [item.name for item in plan[6:]] == [
        f"parallel-10000-workers-{workers}" for workers in DEFAULT_WORKERS
    ]


def test_plan_does_not_create_count_worker_cross_product() -> None:
    plan = build_plan(
        Path("input"),
        Path("run"),
        counts=(1_000, 5_000),
        workers=(2, 4),
        skip_pdf=True,
        allow_custom=True,
    )

    assert [item.kind for item in plan] == [
        "scalability",
        "scalability",
        "parallel",
        "parallel",
    ]


def test_counts_and_worker_validation() -> None:
    assert parse_counts("10000, 1000,10000") == (1_000, 10_000)
    assert parse_workers("8, 2,8") == (2, 8)
    with pytest.raises(argparse.ArgumentTypeError):
        parse_counts("25001")
    with pytest.raises(argparse.ArgumentTypeError):
        parse_workers("0")


def test_scalability_command_uses_python_and_no_shell_syntax() -> None:
    command = build_scalability_command(
        Path("input"), Path("out"), 10_000, 1_000, 4, 42
    )

    assert command[0].endswith("python.exe") or command[0].endswith("python")
    assert "--workers" in command and command[command.index("--workers") + 1] == "4"
    assert "--output-dir" in command
    assert all("&&" not in part and ";" not in part for part in command)


def test_output_root_collision_is_hard_failure() -> None:
    with (
        patch.object(Path, "exists", return_value=True),
        pytest.raises(FileExistsError),
    ):
        create_output_root(Path("unused"), "fixed")


def test_pdf_is_not_planned_by_default_but_can_be_opted_in() -> None:
    with patch(
        "tools.thesis_results.pc_runtime_suite.build_pdf_command",
        return_value=["python", "pdf-benchmark"],
    ):
        default_plan = build_plan(Path("input"), Path("run"))
        pdf_plan = build_plan(Path("input"), Path("run"), skip_pdf=False)

    assert not any(item.kind == "pdf" for item in default_plan)
    assert [item.kind for item in pdf_plan].count("pdf") == 1


def test_visual_is_opt_in() -> None:
    default_plan = build_plan(Path("input"), Path("run"))
    visual_plan = build_plan(Path("input"), Path("run"), skip_visual=False)

    assert not any(item.kind == "visual" for item in default_plan)
    assert [item.kind for item in visual_plan].count("visual") == 1


def test_default_matrix_rejects_unexpected_counts_and_workers() -> None:
    with pytest.raises(ValueError):
        build_plan(Path("input"), Path("run"), counts=(2_000,))
    with pytest.raises(ValueError):
        build_plan(Path("input"), Path("run"), workers=(2, 4, 32))
    with pytest.raises(ValueError):
        build_plan(Path("input"), Path("run"), workers=(16, 17), allow_custom=True)


def test_default_matrix_requires_parallel_count_10000() -> None:
    with pytest.raises(ValueError):
        build_plan(Path("input"), Path("run"), parallel_count=15_000)


def test_custom_parallel_count_is_allowed_only_with_opt_in() -> None:
    plan = build_plan(
        Path("input"), Path("run"), parallel_count=15_000, allow_custom=True
    )

    assert all("15000" in item.name for item in plan[6:])


def test_custom_parallel_count_still_obeys_cutoff() -> None:
    with pytest.raises(ValueError):
        build_plan(Path("input"), Path("run"), parallel_count=25_001, allow_custom=True)


def test_each_default_count_is_present_in_the_scaling_plan() -> None:
    plan = build_plan(
        Path("input"), Path("run"), counts=DEFAULT_COUNTS, skip_parallel=True
    )

    assert [int(item.name.split("-")[1]) for item in plan] == list(DEFAULT_COUNTS)


def test_parse_counts_rejects_empty_and_non_integer_values() -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        parse_counts("")
    with pytest.raises(argparse.ArgumentTypeError):
        parse_counts("1000,abc")


def test_parse_workers_rejects_workers_above_cpu_contract() -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        parse_workers("17")


def test_pdf_can_be_explicitly_disabled() -> None:
    with patch(
        "tools.thesis_results.pc_runtime_suite.build_pdf_command",
        return_value=["python", "pdf-benchmark"],
    ):
        plan = build_plan(Path("input"), Path("run"), skip_pdf=True)

    assert not any(item.kind == "pdf" for item in plan)


def test_visual_opt_in_command_uses_skip_handwriting() -> None:
    visual = next(
        item
        for item in build_plan(Path("input"), Path("run"), skip_visual=False)
        if item.kind == "visual"
    )

    assert "--skip-handwriting" in visual.command


def test_failure_summary_contains_failed_experiment_status() -> None:
    args = argparse.Namespace(
        input_dir=Path("input"),
        output_root=None,
        counts=DEFAULT_COUNTS,
        parallel_count=10_000,
        workers=DEFAULT_WORKERS,
        block_size=1_000,
        seed=42,
        skip_parallel=True,
        skip_pdf=True,
        skip_visual=True,
        allow_custom=False,
        continue_on_error=False,
    )
    writes: list[tuple[Path, object]] = []
    with (
        patch.object(Path, "is_dir", return_value=True),
        patch(
            "tools.thesis_results.pc_runtime_suite.create_output_root",
            return_value=Path("suite"),
        ),
        patch(
            "tools.thesis_results.pc_runtime_suite.write_json_atomic",
            side_effect=lambda path, data: writes.append((path, data)),
        ),
        patch(
            "tools.thesis_results.pc_runtime_suite.run_experiment",
            return_value={"status": "failed", "error": "returncode=7"},
        ),
    ):
        assert run_suite(args) == 1
    summary = cast(
        dict[str, object],
        next(data for path, data in writes if path.name == "suite-summary.json"),
    )
    assert summary["status"] == "failed"
    assert summary["executed_experiment_count"] == 1


def test_failure_and_keyboard_interrupt_are_persisted_without_tempdirs() -> None:
    args = argparse.Namespace(
        input_dir=Path("input"),
        output_root=None,
        counts=DEFAULT_COUNTS,
        parallel_count=10_000,
        workers=DEFAULT_WORKERS,
        block_size=1_000,
        seed=42,
        skip_parallel=True,
        skip_pdf=True,
        skip_visual=True,
        allow_custom=False,
        continue_on_error=False,
    )
    writes: list[tuple[Path, object]] = []
    with (
        patch.object(Path, "is_dir", return_value=True),
        patch(
            "tools.thesis_results.pc_runtime_suite.create_output_root",
            return_value=Path("suite"),
        ),
        patch(
            "tools.thesis_results.pc_runtime_suite.write_json_atomic",
            side_effect=lambda path, data: writes.append((path, data)),
        ),
        patch(
            "tools.thesis_results.pc_runtime_suite.run_experiment",
            return_value={"status": "failed", "error": "returncode=7"},
        ),
    ):
        assert run_suite(args) == 1
    assert any(path.name == "suite-summary.json" for path, _ in writes)

    writes.clear()
    with (
        patch.object(Path, "is_dir", return_value=True),
        patch(
            "tools.thesis_results.pc_runtime_suite.create_output_root",
            return_value=Path("suite"),
        ),
        patch(
            "tools.thesis_results.pc_runtime_suite.write_json_atomic",
            side_effect=lambda path, data: writes.append((path, data)),
        ),
        patch(
            "tools.thesis_results.pc_runtime_suite.run_experiment",
            side_effect=KeyboardInterrupt,
        ),
    ):
        assert run_suite(args) == 130
    summary = cast(
        dict[str, object],
        next(data for path, data in writes if path.name == "suite-summary.json"),
    )
    assert summary["status"] == "aborted"
