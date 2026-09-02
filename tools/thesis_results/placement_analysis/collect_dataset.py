"""Kontrollierte, paarweise Erhebung von `corners`- und `free`-Runs."""

from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


# Input: Datei und Kommandozeilenargumente.
# Output: SHA-256-Fingerprint oder ein `unavailable:`-Wert.
# Der Fingerprint dokumentiert die tatsächlich verwendete Eingabe.
def file_fingerprint(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return f"unavailable:{path.as_posix()}"


# Input: Template, Seed, Modus, Konfiguration und Zielpfad.
# Output: Ausgeführtes argv als Liste.
# Das Template verwendet nur explizite Platzhalter und wird ohne Shell ausgeführt.
def render_command(
    template: str,
    seed: int,
    mode: str,
    output_dir: Path,
    input_path: Path,
    configuration: dict[str, Any] | None = None,
) -> list[str]:
    config = configuration or {}
    if config and "{configuration}" not in template:
        raise ValueError(
            "Nichtleere Konfiguration muss über {configuration} im Kommando "
            "verwendet werden."
        )
    sentinels = {
        "seed": "__COLLECTOR_SEED__",
        "mode": "__COLLECTOR_MODE__",
        "output_dir": "__COLLECTOR_OUTPUT__",
        "input": "__COLLECTOR_INPUT__",
        "configuration": "__COLLECTOR_CONFIGURATION__",
    }
    rendered = template.format(
        seed=sentinels["seed"],
        mode=sentinels["mode"],
        output_dir=sentinels["output_dir"],
        input=sentinels["input"],
        configuration=sentinels["configuration"],
    )
    command = shlex.split(rendered, posix=False)
    replacements = {
        sentinels["seed"]: str(seed),
        sentinels["mode"]: mode,
        sentinels["output_dir"]: str(output_dir),
        sentinels["input"]: str(input_path),
        sentinels["configuration"]: json.dumps(config, sort_keys=True),
    }
    return [replacements.get(argument, argument) for argument in command]


# Input: Collector-CLI-Argumente.
# Output: Exit-Code 0; schreibt ein neues JSONL-Erhebungsmanifest.
# Fehlerhafte und abgelehnte Prozesse bleiben als Einträge im Manifest erhalten.
def collect_dataset(
    template: str,
    seeds: list[int],
    input_path: Path,
    output_dir: Path,
    manifest_path: Path,
    configuration: dict[str, Any],
) -> int:
    if len(set(seeds)) < 100:
        raise ValueError(
            "Die kontrollierte Erhebung benötigt mindestens 100 unterschiedliche Seeds."
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    input_hash = file_fingerprint(input_path)
    records: list[dict[str, Any]] = []
    for seed in seeds:
        for mode in ("corners", "free"):
            run_dir = output_dir / f"seed-{seed:06d}" / mode
            run_dir.mkdir(parents=True, exist_ok=True)
            command = render_command(
                template, seed, mode, run_dir, input_path, configuration
            )
            try:
                completed = subprocess.run(
                    command, check=False, capture_output=True, text=True
                )
                status = (
                    "successful" if completed.returncode == 0 else "unexpected_failed"
                )
                error = completed.stderr[-2000:] if completed.returncode else ""
            except OSError as exc:
                status, error = "unexpected_failed", str(exc)
                completed = None
            records.append(
                {
                    "seed": seed,
                    "placement_mode": mode,
                    "command": command,
                    "input_fingerprint": input_hash,
                    "configuration": configuration,
                    "output_path": run_dir.as_posix(),
                    "status": status,
                    "return_code": completed.returncode if completed else None,
                    "error": error,
                }
            )
    manifest = {
        "created_at": datetime.now(UTC).isoformat(),
        "seed_count": len(set(seeds)),
        "modes": ["corners", "free"],
        "configuration": configuration,
        "input": input_path.as_posix(),
        "input_fingerprint": input_hash,
        "records": records,
        "status_counts": {
            status: sum(record["status"] == status for record in records)
            for status in ("successful", "unexpected_failed", "controlled_rejected")
        },
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return 0


# Input: `sys.argv`-ähnliche Collector-Argumente.
# Output: Exit-Code des Collectors.
# Die Ausgabe wird in einen separat angegebenen Ordner geschrieben.
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--command-template",
        required=True,
        help="Template mit {seed}, {mode}, {output_dir}, {input}",
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--seed", type=int, action="append", dest="seeds")
    parser.add_argument(
        "--configuration",
        default="{}",
        help="JSON-Konfiguration, identisch für beide Modi",
    )
    args = parser.parse_args(argv)
    seeds = args.seeds or list(range(100))
    configuration = json.loads(args.configuration)
    if not isinstance(configuration, dict):
        parser.error("--configuration muss ein JSON-Objekt sein.")
    return collect_dataset(
        args.command_template,
        seeds,
        args.input,
        args.output_dir,
        args.manifest,
        configuration,
    )


if __name__ == "__main__":
    raise SystemExit(main())
