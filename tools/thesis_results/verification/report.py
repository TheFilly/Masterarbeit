"""Stabile JSON-/CSV-Berichte fuer qualitative Evaluationen."""

from __future__ import annotations

import csv
import json
import platform
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .case_outcomes import (
    ArtifactStatus,
    Balance,
    CaseOutcome,
    CaseProfile,
    CaseResult,
    has_valid_rejection_evidence,
)

_BALANCE_RESULT_FIELDS = (
    "successful",
    "rejected",
    "unexpected_failed",
    "ground_truth_present",
    "ground_truth_missing",
    "unparseable_artifacts",
    "invalid_annotations",
    "path_collisions",
    "clipping_errors",
    "geometry_errors",
    "input_output_differences",
    "completed_documents",
    "output_bytes",
)


# Input: Persistierte rohe CaseResults, erwartete Fallmenge und Blocknummer.
# Output: Unabhaengig rekonstruierte Bilanz sowie konkrete Validierungsbefunde.
def reconstruct_case_result_balance(
    raw_results: list[Any],
    planned: int,
    *,
    manifest_cases: dict[str, str],
    block_number: int | None = None,
) -> tuple[Balance | None, list[str]]:
    differences: list[str] = []
    parsed: list[CaseResult] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_results):
        if not isinstance(raw, dict):
            differences.append(f"CaseResult[{index}] ist kein Objekt")
            continue
        try:
            payload = dict(raw)
            payload["outcome"] = CaseOutcome(str(payload["outcome"]))
            payload["artifact_status"] = ArtifactStatus(
                str(payload.get("artifact_status", ArtifactStatus.MISSING.value))
            )
            profile = payload.get("profile")
            if isinstance(profile, dict):
                profile_payload = dict(profile)
                if "profile_status" in profile_payload:
                    from .case_outcomes import ProfileStatus

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
            result = CaseResult(**payload)
        except (TypeError, ValueError, KeyError) as error:
            differences.append(f"CaseResult[{index}] ist ungueltig: {error}")
            continue
        if result.case_id in seen:
            differences.append(f"Doppelte CaseResult-ID: {result.case_id}")
        seen.add(result.case_id)
        expected_fingerprint = manifest_cases.get(result.case_id)
        if expected_fingerprint is None:
            differences.append(f"Unbekannte CaseResult-ID: {result.case_id}")
        elif result.source_fingerprint != expected_fingerprint:
            differences.append(f"Source-Fingerprint abweichend: {result.case_id}")
        if block_number is not None and result.block_number is None:
            differences.append(f"Blocknummer fehlt: {result.case_id}")
        if (
            block_number is not None
            and result.block_number is not None
            and result.block_number > block_number
        ):
            differences.append(
                f"CaseResult liegt in zukuenftigem Block: {result.case_id}"
            )
        if result.output_bytes < 0 or any(
            value < 0
            for value in (
                result.ground_truth_files,
                result.expected_ground_truth_files,
                result.unparseable_artifacts,
                result.invalid_annotations,
                result.path_collisions,
                result.clipping_errors,
                result.geometry_errors,
                result.input_output_differences,
            )
        ):
            differences.append(f"Negative CaseResult-Metrik: {result.case_id}")
        if result.outcome.value == "successful" and (
            result.artifact_status.value != "valid"
            or result.ground_truth_files != result.expected_ground_truth_files
        ):
            differences.append(f"Erfolg ohne gueltige Ground Truth: {result.case_id}")
        if result.input_output_status not in {
            None,
            "same",
            "same_with_warnings",
            "different",
            "unsupported",
            "unavailable",
        }:
            differences.append(f"Unbekannter Input/Output-Status: {result.case_id}")
        if result.outcome.value == "rejected" and not has_valid_rejection_evidence(
            result
        ):
            differences.append(f"Ablehnung ohne validierte Evidenz: {result.case_id}")
        parsed.append(result)
    try:
        balance = Balance.from_results(parsed, planned)
    except ValueError as error:
        differences.append(f"CaseResult-Bilanz nicht rekonstruierbar: {error}")
        return None, differences
    if balance.completed_documents != len(parsed):
        differences.append("completed_documents stimmt nicht mit CaseResults ueberein")
    return balance, differences


# Input: Unabhaengig rekonstruierte Bilanz und persistierte Summary-Bilanz.
# Output: Feldgenaue Differenzen fuer die Review-/Checkpoint-Freigabe.
def compare_balance_fields(
    reconstructed: Balance, stored: dict[str, Any], *, label: str
) -> list[str]:
    differences: list[str] = []
    expected = asdict(reconstructed)
    for field_name in ("planned", *_BALANCE_RESULT_FIELDS):
        if stored.get(field_name) != expected[field_name]:
            differences.append(
                f"{label}: Bilanzfeld {field_name} passt nicht zur Rekonstruktion"
            )
    return differences


# Input: Persistierte Blocksummary und der zugehoerige Checkpoint.
# Output: Feldgenaue Statusdifferenzen unabhaengig von der Bilanz.
def compare_block_summary_fields(
    summary: dict[str, Any], checkpoint: dict[str, Any], *, label: str
) -> list[str]:
    differences: list[str] = []
    fields = (
        "block_number",
        "block_size",
        "seed",
        "workers",
        "mode",
        "elapsed_seconds",
        "output_bytes",
        "peak_memory_bytes",
        "abort_reason",
    )
    for field_name in fields:
        if summary.get(field_name) != checkpoint.get(field_name):
            differences.append(f"{label}: Statusfeld {field_name} abweichend")
    for field_name in (
        "terminal_case_ids",
        "in_progress_case_ids",
        "open_case_ids",
    ):
        if sorted(summary.get(field_name, [])) != sorted(
            checkpoint.get(field_name, [])
        ):
            differences.append(f"{label}: Statusfeld {field_name} abweichend")
    if summary.get("status") != checkpoint.get("block_status"):
        differences.append(f"{label}: Statusfeld status abweichend")
    summary_balance = summary.get("balance")
    checkpoint_balance = checkpoint.get("balance")
    if isinstance(summary_balance, dict) and isinstance(checkpoint_balance, dict):
        for field_name in asdict(Balance()):
            if summary_balance.get(field_name) != checkpoint_balance.get(field_name):
                differences.append(
                    f"{label}: Kumulativfeld balance.{field_name} abweichend"
                )
    else:
        differences.append(f"{label}: Balance fehlt")
    return differences


def environment_metadata() -> dict[str, str]:
    """Liefert reproduzierbare Laufzeitmetadaten."""
    return {
        "python": sys.version,
        "platform": platform.platform(),
        "implementation": platform.python_implementation(),
    }


def aggregate_profiles(profiles: list[CaseProfile]) -> dict[str, Any]:
    """Aggregiert Profile absolut, relativ und nach Fixture-Wiederverwendung."""
    fields = (
        "document_type",
        "photometry",
        "width",
        "height",
        "size_class",
        "frame_mode",
        "supported",
        "placement_mode",
        "rotation_degrees",
        "font_or_renderer",
        "profile_status",
    )
    unique = len({profile.source_fingerprint for profile in profiles})
    result: dict[str, Any] = {
        "case_instances": len(profiles),
        "unique_sources": unique,
        "reuse_factor": len(profiles) / unique if unique else 0.0,
        "evaluation_kind": "unique_input_evaluation"
        if len(profiles) <= unique
        else "fixture_reuse_endurance",
    }
    for field_name in fields:
        counts: dict[str, int] = {}
        for profile in profiles:
            key = str(getattr(profile, field_name))
            counts[key] = counts.get(key, 0) + 1
        result[field_name] = {
            key: {"count": count, "share": count / len(profiles) if profiles else 0.0}
            for key, count in sorted(counts.items())
        }
    structured = {"expected": 0, "present": 0, "used": 0, "missing": 0}
    for profile in profiles:
        structured["expected"] += len(profile.expected_schema_fields)
        structured["present"] += len(profile.present_structured_fields)
        structured["used"] += len(profile.used_structured_fields)
        structured["missing"] += len(profile.missing_expected_fields)
    result["structured_fields"] = structured
    result["source_fingerprints"] = {
        fingerprint: sum(
            profile.source_fingerprint == fingerprint for profile in profiles
        )
        for fingerprint in sorted({profile.source_fingerprint for profile in profiles})
    }
    result["profile_reasons"] = {
        str(reason): sum(profile.profile_reason == reason for profile in profiles)
        for reason in sorted({profile.profile_reason for profile in profiles}, key=str)
    }
    result["structured_fields_by_name"] = {
        field: {
            "expected": sum(
                field in profile.expected_schema_fields for profile in profiles
            ),
            "present": sum(
                field in profile.present_structured_fields for profile in profiles
            ),
            "used": sum(
                field in profile.used_structured_fields for profile in profiles
            ),
            "missing": sum(
                field in profile.missing_expected_fields for profile in profiles
            ),
        }
        for field in sorted(
            {field for profile in profiles for field in profile.expected_schema_fields}
        )
    }
    return result


# Input: Evaluation-Root, Fallresultate und optionale Laufmetadaten.
# Output: JSON-Rohbericht, flacher stabiler Fall-CSV und separates Profil-JSON.
# Verschachtelte Profile werden nicht in CSV-Zellen serialisiert.
def write_report(
    root: Path, results: list[CaseResult], metadata: dict[str, Any] | None = None
) -> tuple[Path, Path]:
    root.mkdir(parents=True, exist_ok=True)
    json_path, csv_path = (
        root / "evaluation-results.json",
        root / "evaluation-results.csv",
    )
    profiles = [result.profile for result in results if result.profile is not None]
    payload = {
        "environment": environment_metadata(),
        "metadata": metadata or {},
        "results": [asdict(result) for result in results],
        "profile_aggregate": aggregate_profiles(profiles),
        "outcome_counts": {
            outcome: sum(result.outcome.value == outcome for result in results)
            for outcome in ("successful", "rejected", "unexpected_failed")
        },
        "block_summaries": _load_block_summaries(root),
        "run_balance": _load_json_object(root / "run-summary.json"),
        "evaluation_metrics": _load_json_object(root / "evaluation-metrics.json"),
        "checkpoint_consistency": checkpoint_consistency(root),
    }
    json_path.write_text(
        json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8"
    )
    columns = [
        "case_id",
        "outcome",
        "source_fingerprint",
        "artifact_status",
        "error_code",
        "ground_truth_files",
        "expected_ground_truth_files",
        "unparseable_artifacts",
        "invalid_annotations",
        "path_collisions",
        "clipping_errors",
        "geometry_errors",
        "input_output_status",
        "input_output_reason",
        "input_output_warnings",
        "input_output_tolerance",
        "input_output_max_absolute_difference",
        "input_output_mean_absolute_difference",
        "input_output_p99_absolute_difference",
        "input_output_pixels_compared",
        "input_output_pixels_exceeding_tolerance",
        "input_output_pixels_exceeding_quality_limit",
        "input_output_large_difference_fraction",
        "input_output_quality_rule",
        "output_bytes",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for result in results:
            row = asdict(result)
            writer.writerow(
                {
                    column: (
                        json.dumps(row.get(column), ensure_ascii=False)
                        if column
                        in {
                            "input_output_warnings",
                            "input_output_quality_rule",
                        }
                        else row.get(column)
                    )
                    for column in columns
                }
            )
    (root / "profile-aggregate.json").write_text(
        json.dumps(aggregate_profiles(profiles), indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    return json_path, csv_path


# Input: Evaluation-Root mit persistierten Blockreports.
# Output: Stabil sortierte Blocksummary-Liste fuer Blockauswertungen.
def _load_block_summaries(root: Path) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for path in sorted(root.glob("block-*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            summary = payload.get("summary")
            if isinstance(summary, dict):
                summaries.append(summary)
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
    return summaries


# Input: Evaluation-Root mit Checkpoint und Commit-Paket.
# Output: Expliziter Konsistenzstatus fuer die Reportfreigabe.
def checkpoint_consistency(root: Path) -> dict[str, Any]:
    checkpoint_path = root / "checkpoint.json"
    if not checkpoint_path.is_file():
        return {"status": "unavailable", "reason": "Checkpoint fehlt"}
    differences: list[str] = []
    try:
        checkpoint = _load_json_object(checkpoint_path)
        commits_root = root / ".commits"
        package_dirs = sorted(
            path
            for path in commits_root.glob("block-[0-9][0-9][0-9][0-9][0-9][0-9]")
            if path.is_dir()
        )
        extra_packages = (
            sorted(
                path.name
                for path in commits_root.iterdir()
                if path.is_dir() and path not in package_dirs
            )
            if commits_root.is_dir()
            else []
        )
        differences.extend(f"Zusatz-/Orphan-Paket: {name}" for name in extra_packages)
        sequence: list[int] = []
        cumulative_ids: set[str] = set()
        previous_ids: set[str] = set()
        expected_config = checkpoint.get("config_fingerprint")
        expected_input = checkpoint.get("input_fingerprint")
        manifest_cases: dict[str, str] = {}
        manifest = _load_json_object(root / "input-manifest.json")
        for item in manifest.get("cases", []):
            if isinstance(item, dict) and "case_id" in item:
                manifest_cases[str(item["case_id"])] = str(
                    item.get("source_fingerprint", "")
                )
        package_summaries: list[dict[str, Any]] = []
        latest_reconstructed: Balance | None = None
        historical_results: dict[str, str] = {}
        for package_dir in package_dirs:
            name = package_dir.name
            try:
                number = int(name.rsplit("-", 1)[-1])
                package_checkpoint = _load_json_object(package_dir / "checkpoint.json")
                package_block = _load_json_object(package_dir / "block.json")
                result_payload = _load_json_object(package_dir / "case-results.json")
                raw_results = result_payload.get("results")
                if not isinstance(raw_results, list):
                    raise ValueError("case-results.json ohne results-Liste")
                reconstructed, result_differences = reconstruct_case_result_balance(
                    raw_results,
                    len(manifest_cases),
                    manifest_cases=manifest_cases,
                    block_number=number,
                )
                differences.extend(f"{name}: {detail}" for detail in result_differences)
                for item in raw_results:
                    if not isinstance(item, dict) or "case_id" not in item:
                        continue
                    case_id = str(item["case_id"])
                    serialized = json.dumps(item, sort_keys=True, default=str)
                    if (
                        case_id in historical_results
                        and historical_results[case_id] != serialized
                    ):
                        differences.append(
                            f"{name}: historisches CaseResult wurde veraendert: "
                            f"{case_id}"
                        )
                    historical_results.setdefault(case_id, serialized)
                result_ids = [
                    str(item.get("case_id"))
                    for item in raw_results
                    if isinstance(item, dict)
                ]
                if len(result_ids) != len(raw_results) or len(set(result_ids)) != len(
                    result_ids
                ):
                    differences.append(
                        f"{name}: ungueltige oder doppelte CaseResult-IDs"
                    )
                for item in raw_results:
                    if not isinstance(item, dict) or item.get("outcome") not in {
                        "successful",
                        "rejected",
                        "unexpected_failed",
                    }:
                        differences.append(f"{name}: ungueltige Fallklassifikation")
                        continue
                    case_id = str(item.get("case_id"))
                    if manifest_cases and (
                        case_id not in manifest_cases
                        or str(item.get("source_fingerprint"))
                        != manifest_cases[case_id]
                    ):
                        differences.append(
                            f"{name}: CaseResult passt nicht zum Input-Manifest"
                        )
                checkpoint_ids = {
                    str(item)
                    for item in package_checkpoint.get("terminal_case_ids", [])
                }
                block_ids = {
                    str(item) for item in package_block.get("completed_case_ids", [])
                }
                if set(result_ids) != checkpoint_ids or checkpoint_ids != block_ids:
                    differences.append(
                        f"{name}: CaseResult-/Checkpoint-/Block-IDs unterscheiden sich"
                    )
                if not previous_ids <= checkpoint_ids:
                    differences.append(f"{name}: kumulative CaseResult-Menge schrumpft")
                parent_ids = {
                    str(item)
                    for item in package_checkpoint.get("parent_terminal_case_ids", [])
                }
                if parent_ids != previous_ids or checkpoint_ids == previous_ids:
                    differences.append(
                        f"{name}: Parent-/Kumulativkette ist inkonsistent"
                    )
                previous_ids = checkpoint_ids
                cumulative_ids |= checkpoint_ids
                if package_checkpoint.get("config_fingerprint") != expected_config:
                    differences.append(f"{name}: Konfigurationsfingerprint abweichend")
                if package_checkpoint.get("input_fingerprint") != expected_input:
                    differences.append(f"{name}: Inputfingerprint abweichend")
                summary = package_block.get("summary")
                balance = summary.get("balance") if isinstance(summary, dict) else None
                if (
                    not isinstance(summary, dict)
                    or summary.get("block_number") != number
                ):
                    differences.append(f"{name}: Blocknummer im Summary stimmt nicht")
                if not isinstance(balance, dict):
                    differences.append(f"{name}: Blockbilanz fehlt")
                else:
                    summary_payload = summary if isinstance(summary, dict) else {}
                    differences.extend(
                        compare_block_summary_fields(
                            summary_payload, package_checkpoint, label=name
                        )
                    )
                    package_balance = package_checkpoint.get("balance", {})
                    if reconstructed is not None:
                        differences.extend(
                            compare_balance_fields(
                                reconstructed, balance, label=name + "/block"
                            )
                        )
                        differences.extend(
                            compare_balance_fields(
                                reconstructed,
                                package_balance,
                                label=name + "/checkpoint",
                            )
                        )
                        latest_reconstructed = reconstructed
                sequence.append(number)
                package_summaries.append(
                    {
                        "block_number": number,
                        "balance": balance or {},
                        "case_ids": sorted(checkpoint_ids),
                    }
                )
            except (
                OSError,
                UnicodeError,
                json.JSONDecodeError,
                TypeError,
                ValueError,
            ) as error:
                differences.append(f"{name}: {error}")
                sequence.append(int(name.rsplit("-", 1)[-1]))
        if sequence != list(range(1, len(sequence) + 1)):
            differences.append("Commitpakete bilden keine lueckenlose Blocksequenz")
        commit_name = checkpoint.get("commit_directory")
        if not isinstance(commit_name, str):
            differences.append("Checkpoint ohne Commitreferenz")
        else:
            latest = package_summaries[-1] if package_summaries else None
            terminal_ids = {
                str(item) for item in checkpoint.get("terminal_case_ids", [])
            }
            if latest is None or terminal_ids != set(latest["case_ids"]):
                differences.append(
                    "Gesamtcheckpoint passt nicht zum letzten Commitpaket"
                )
            if terminal_ids != cumulative_ids:
                differences.append(
                    "Gesamtcheckpoint passt nicht zur kumulativen Paketbilanz"
                )
            if latest is not None:
                final_balance = checkpoint.get("balance", {})
                if (
                    latest_reconstructed is not None
                    and checkpoint.get("block_status") == "completed"
                ):
                    differences.extend(
                        compare_balance_fields(
                            latest_reconstructed,
                            final_balance,
                            label="Gesamtcheckpoint",
                        )
                    )
        return {
            "status": "consistent" if not differences else "inconsistent",
            "reason": None if not differences else "; ".join(differences),
            "differences": differences,
            "commit_directory": checkpoint.get("commit_directory"),
            "terminal_case_count": len(cumulative_ids),
            "block_numbers": sequence,
            "block_summaries": package_summaries,
            "orphan_packages": extra_packages,
        }
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        TypeError,
        ValueError,
    ) as error:
        return {
            "status": "inconsistent",
            "reason": str(error),
            "differences": [str(error)],
        }


# Input: JSON-Datei.
# Output: Objektpayload oder leerer Objektstatus bei fehlendem Abschlussreport.
def _load_json_object(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} enthaelt kein Objekt")
    return payload
