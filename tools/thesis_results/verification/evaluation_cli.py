"""Ausfuehrbarer Einstieg fuer manifestbasierte Evaluationen."""

from __future__ import annotations

import argparse
import importlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from .case_outcomes import CaseResult, EvaluationConfig
from .evaluation_runner import EvaluationRunner, PlannedCase, source_fingerprint
from .report import write_report
from .semantic_comparison import profile_source

PipelineCallback = Callable[[PlannedCase, Path], CaseResult]


# Input: Manifest-JSON mit source-Pfaden und optionalen Negativfallmarkierungen.
# Output: stabile PlannedCase-Liste mit Profilen und Fingerprints.
# Quellen werden vor dem ersten Block profiliert; nicht parsbare Quellen bleiben
# als geplante Faelle erhalten und erhalten den Status unavailable.
def load_cases(manifest: Path) -> list[PlannedCase]:
    """Laedt und profiliert die vollstaendige Eingabefallliste."""
    payload = json.loads(manifest.read_text(encoding="utf-8-sig"))
    entries = payload["cases"] if isinstance(payload, dict) else payload
    schema_fields = _schema_fields(payload, manifest)
    cases: list[PlannedCase] = []
    for index, entry in enumerate(entries):
        source = Path(entry["source"])
        if not source.is_absolute():
            source = manifest.parent / source
        case_id = str(entry.get("case_id", f"case-{index:06d}"))
        try:
            fingerprint = source_fingerprint(source)
        except OSError:
            fingerprint = f"unavailable:{source.as_posix()}"
        profile = profile_source(
            source,
            case_id,
            tuple(entry.get("expected_schema_fields", schema_fields)),
            tuple(entry.get("used_schema_fields", ())),
            placement_mode=entry.get("placement_mode"),
            rotation_degrees=entry.get("rotation_degrees"),
            font_or_renderer=entry.get("font_or_renderer", entry.get("font_family")),
            handwriting_options={
                key: entry[key]
                for key in ("handwriting_ink_color", "handwriting_contrast_mode")
                if key in entry
            },
            render_options={
                key: entry[key]
                for key in (
                    "font_size_pct",
                    "font_family",
                    "text_background",
                    "renderer",
                    "placement_mode",
                    "rotation_degrees",
                    "handwriting_ink_color",
                    "handwriting_contrast_mode",
                )
                if key in entry
            },
        )
        cases.append(
            PlannedCase(
                case_id,
                source,
                fingerprint,
                str(entry.get("document_type", source.suffix.lstrip("."))),
                profile,
                bool(entry.get("expected_rejection", False)),
                bool(entry.get("planned_negative", False)),
            )
        )
    return cases


# Input: Manifestpayload und Manifestpfad.
# Output: Identifier-Feldnamen aus Schema oder explizitem Fallback.
def _schema_fields(payload: Any, manifest: Path) -> tuple[str, ...]:
    schema_value = (
        payload.get("identifier_schema", payload.get("identifier_schema_path"))
        if isinstance(payload, dict)
        else None
    )
    schema_path = Path(str(schema_value)) if schema_value else None
    if schema_path is not None and not schema_path.is_absolute():
        schema_path = manifest.parent / schema_path
    if schema_path is None:
        return ()
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8-sig"))
        fields = schema.get("fields", [])
        return tuple(
            str(field["name"])
            for field in fields
            if isinstance(field, dict) and "name" in field
        )
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, KeyError):
        return ()


def _load_callback(reference: str) -> PipelineCallback:
    """Laedt einen explizit angegebenen Pipeline-Callback."""
    module_name, separator, function_name = reference.partition(":")
    if not separator:
        raise ValueError("Callback muss als modul:funktion angegeben werden.")
    value = getattr(importlib.import_module(module_name), function_name)
    return cast(PipelineCallback, value)


# Input: Input-Manifest, Evaluation-Root und bestehender Pipeline-Callback.
# Output: Vollstaendige Balance und Reports ausschliesslich im Evaluation-Root.
# Der Callbackvertrag erlaubt die Verwendung bestehender Produktions-APIs,
# waehrend die Evaluationsschicht keine Produktionslogik importseitig veraendert.
def run_evaluation(
    manifest: Path,
    workspace: Path,
    callback: PipelineCallback,
    *,
    seed: int = 42,
    workers: int = 1,
    mode: str = "sequential",
    block_size: int = 100,
    resume: bool = False,
) -> Any:
    """Fuehrt Manifest, Pipeline, Bundlepruefung und Report in einem Lauf aus."""
    cases = load_cases(manifest)
    config = EvaluationConfig(
        seed=seed, workers=workers, mode=mode, block_size=block_size
    )
    runner = EvaluationRunner(workspace, config)
    balance = runner.run(cases, callback, resume=resume)
    results = runner._results_from_checkpoint(runner._load_checkpoint())
    write_report(
        workspace,
        results,
        {"seed": seed, "workers": workers, "mode": mode, "block_size": block_size},
    )
    return balance


def main() -> int:
    """Startet die manifestbasierte Evaluation ueber `python -m`."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, default=Path("thesis-results"))
    parser.add_argument("--callback", required=True, help="modul:funktion")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--mode", default="sequential")
    parser.add_argument("--block-size", type=int, default=100)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    run_evaluation(
        args.manifest,
        args.workspace,
        _load_callback(args.callback),
        seed=args.seed,
        workers=args.workers,
        mode=args.mode,
        block_size=args.block_size,
        resume=args.resume,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
