from argparse import Namespace
from datetime import datetime

import pytest

from injection_pipeline.config.identifier_schema import DEFAULT_IDENTIFIER_SCHEMA_PATH
from injection_pipeline.runtime import cli
from injection_pipeline.runtime.options import (
    DEFAULT_HANDWRITING_CHECKPOINT_PATH,
    DEFAULT_OUTPUT_DIR,
    FONT_FAMILY_CHOICES,
    HANDWRITING_FONT_FAMILY,
)


def test_font_family_choices_include_handwriting() -> None:
    assert HANDWRITING_FONT_FAMILY in FONT_FAMILY_CHOICES


def test_generate_handwriting_subcommand_delegates_to_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_args: list[Namespace] = []

    def fake_generate(args: Namespace) -> object:
        captured_args.append(args)
        return object()

    monkeypatch.setattr(cli, "generate_handwriting_assets", fake_generate)
    monkeypatch.setattr(
        cli.sys,
        "argv",
        ["injection-pipeline", "generate-handwriting", "--seed", "123"],
    )

    cli.main()

    assert captured_args[0].seed == 123
    assert captured_args[0].handwriting_checkpoint == str(
        DEFAULT_HANDWRITING_CHECKPOINT_PATH
    )


def test_interactive_prompts_seed_then_font(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prompts: list[str] = []
    answers = iter(
        [
            "77",
            "handwriting",
            "y",
            "",
            "0",
            "100",
            "corners",
            "n",
            "n",
            "",
        ]
    )

    def fake_input(prompt: str) -> str:
        prompts.append(prompt)
        return next(answers)

    monkeypatch.setattr("builtins.input", fake_input)

    args = cli._collect_interactive_args()

    assert args.seed == 77
    assert args.font_family == HANDWRITING_FONT_FAMILY
    assert _prompt_names(prompts)[:2] == ["seed", "font-family"]


def test_cli_allows_handwriting_font_with_explicit_manifest_mappings() -> None:
    args = _base_args(
        font_family=HANDWRITING_FONT_FAMILY,
        handwriting_manifest="manifest.json",
        handwriting_asset=[
            "patient_name=name-asset",
            "patient_id=id-asset",
            "accession_number=acc-asset",
        ],
    )

    cli._validate_args(args)


def test_cli_rejects_handwriting_manifest_without_mappings() -> None:
    args = _base_args(
        font_family=HANDWRITING_FONT_FAMILY,
        handwriting_manifest="manifest.json",
        handwriting_asset=[],
    )

    with pytest.raises(ValueError, match="requires --handwriting-asset mappings"):
        cli._validate_args(args)


def _prompt_names(prompts: list[str]) -> list[str]:
    return [prompt.split(":", 1)[0] for prompt in prompts]


def _base_args(**overrides: object) -> Namespace:
    values = {
        "seed": 42,
        "input": None,
        "output_dir": str(DEFAULT_OUTPUT_DIR),
        "identifier_schema": str(DEFAULT_IDENTIFIER_SCHEMA_PATH),
        "handwriting_manifest": None,
        "handwriting_asset": [],
        "rotation_angle": 0,
        "font_size_pct": 100,
        "placement_mode": "corners",
        "font_family": "arial",
        "text_background": None,
        "show_label_boxes": "n",
        "run_timestamp": datetime(2026, 7, 15, 12, 0, 0),
    }
    values.update(overrides)
    return Namespace(**values)
