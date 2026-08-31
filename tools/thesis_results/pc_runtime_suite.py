"""Sichere, begrenzte PC-Laufzeitsuite fuer Thesis-Benchmarks."""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_COUNTS = (1_000, 5_000, 10_000, 15_000, 20_000, 25_000)
DEFAULT_WORKERS = (2, 4, 6, 8, 16)
MAX_COUNT = 25_000
MAX_WORKERS = 16


@dataclass(frozen=True)
class Experiment:
    """Ein einzelner, separat ausgefuehrter Benchmarkprozess."""

    name: str
    kind: str
    command: list[str]
    output_dir: str


# Input: Eine kommagetrennte Liste positiver Dokumentzahlen.
# Output: Aufsteigend sortierte, eindeutige Dokumentzahlen bis 25.000.
# Ungueltige oder zu grosse Werte werden vor der Ausfuehrung abgewiesen.
def parse_counts(value: str) -> tuple[int, ...]:
    try:
        counts = tuple(sorted({int(part.strip()) for part in value.split(",")}))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("counts muss Ganzzahlen enthalten.") from exc
    if not counts or any(count < 1 or count > MAX_COUNT for count in counts):
        raise argparse.ArgumentTypeError("counts muss Werte von 1 bis 25000 enthalten.")
    return counts


# Input: Eine kommagetrennte Liste positiver Workerzahlen.
# Output: Aufsteigend sortierte, eindeutige Workerzahlen.
# Die tatsaechliche Verfuegbarkeit wird vom Benchmarkprozess bestimmt; die Suite
# erzeugt keine Experimente fuer nicht angeforderte Kombinationen.
def parse_workers(value: str) -> tuple[int, ...]:
    try:
        workers = tuple(sorted({int(part.strip()) for part in value.split(",")}))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("workers muss Ganzzahlen enthalten.") from exc
    if not workers or any(worker < 1 or worker > MAX_WORKERS for worker in workers):
        raise argparse.ArgumentTypeError("workers muss zwischen 1 und 16 liegen.")
    return workers


# Input: Ausgabeparent und optional eine vorgegebene Lauf-ID.
# Output: Neuer, noch nicht existierender Suite-Ordner.
# Der Ordner wird mit exist_ok=False angelegt; vorhandene explizite Ziele brechen
# hart ab, damit keine Benchmarks oder Zwischenstaende ueberschrieben werden.
def create_output_root(parent: Path, run_id: str | None = None) -> Path:
    parent = parent.expanduser().resolve()
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    identifier = run_id or f"{timestamp}-{uuid.uuid4().hex[:8]}"
    root = parent / f"pc-runtime-{identifier}"
    if root.exists():
        raise FileExistsError(f"Ausgabeordner existiert bereits: {root}")
    root.mkdir(parents=True, exist_ok=False)
    return root


# Input: Beliebige JSON-Daten und ein Zielpfad innerhalb des neuen Suite-Ordners.
# Output: Keine Rueckgabe; schreibt atomar ueber eine temporaere Nachbardatei.
# So bleiben Manifest und Summary auch bei einem Prozessabbruch in einem
# vollstaendigen vorherigen Zustand erhalten.
def write_json_atomic(path: Path, data: object) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


# Input: Eingabeordner, Zielordner und Laufparameter.
# Output: Sichere Argumentliste fuer den bestehenden Skalierbarkeitsbenchmark.
# Die Rueckgabe ist fuer subprocess ohne Shell-Evaluation bestimmt.
def build_scalability_command(
    input_dir: Path,
    output_dir: Path,
    count: int,
    block_size: int,
    workers: int,
    seed: int,
) -> list[str]:
    if count > MAX_COUNT:
        raise ValueError("Die Suite erlaubt hoechstens 25000 Dokumente.")
    return [
        sys.executable,
        "-m",
        "tools.thesis_results.performance.scalability_benchmark",
        "--input-dir",
        str(input_dir),
        "--count",
        str(count),
        "--block-size",
        str(block_size),
        "--workers",
        str(workers),
        "--seed",
        str(seed),
        "--output-dir",
        str(output_dir),
    ]


# Input: Eingabeordner und neuer Suite-Ordner mit PDF-Unterordner.
# Output: PDF-Benchmarkargumentliste oder None, wenn keine passende Quelle existiert.
# PDF wird optional geplant; fehlende lokale Vorlagen werden transparent als
# nicht ausfuehrbar behandelt, ohne andere Experimente zu veraendern.
def build_pdf_command(input_dir: Path, output_dir: Path, seed: int) -> list[str] | None:
    pdfs = sorted(input_dir.rglob("*.pdf"))
    images = sorted(
        path for suffix in ("*.jpg", "*.jpeg") for path in input_dir.rglob(suffix)
    )
    if not pdfs or not images:
        return None
    return [
        sys.executable,
        "-m",
        "tools.thesis_results.performance.pdf_scaling_benchmark",
        "--template",
        str(pdfs[0]),
        "--image",
        str(images[0]),
        "--max-images",
        "16",
        "--repetitions",
        "5",
        "--seed",
        str(seed),
        "--output-dir",
        str(output_dir),
    ]


# Input: Eingabeordner, Suite-Ordner und alle CLI-Messparameter.
# Output: Ueberschaubare, nicht-kreuzproduktartige Experimentliste.
# Die Skalierungsreihe nutzt nur Worker 1; die Parallelreihe ist ausschliesslich
# fuer parallel_count vorgesehen und enthaelt die Worker-Baseline 1 nicht erneut.
def build_plan(
    input_dir: Path,
    output_root: Path,
    counts: tuple[int, ...] = DEFAULT_COUNTS,
    parallel_count: int = 10_000,
    workers: tuple[int, ...] = DEFAULT_WORKERS,
    block_size: int = 1_000,
    seed: int = 42,
    skip_parallel: bool = False,
    skip_pdf: bool = True,
    skip_visual: bool = True,
    allow_custom: bool = False,
) -> list[Experiment]:
    if (
        block_size < 1
        or parallel_count < 1
        or parallel_count > MAX_COUNT
        or any(count < 1 or count > MAX_COUNT for count in counts)
        or any(worker < 1 or worker > MAX_WORKERS for worker in workers)
    ):
        raise ValueError(
            "counts und parallel-count muessen zwischen 1 und 25000 liegen; "
            "block-size und workers muessen positiv sein."
        )
    if not allow_custom and (
        counts != DEFAULT_COUNTS
        or workers != DEFAULT_WORKERS
        or parallel_count != 10_000
    ):
        raise ValueError(
            "Die Standardsuite erlaubt nur die vereinbarte Count-/Worker-Matrix. "
            "Fuer abweichende Reihen --allow-custom verwenden."
        )
    experiments: list[Experiment] = []
    for count in counts:
        directory = output_root / f"scalability-{count:05d}-workers-1"
        experiments.append(
            Experiment(
                f"scalability-{count:05d}-workers-1",
                "scalability",
                build_scalability_command(
                    input_dir, directory, count, block_size, 1, seed
                ),
                str(directory),
            )
        )
    if not skip_parallel:
        for worker_count in workers:
            directory = output_root / (
                f"parallel-{parallel_count:05d}-workers-{worker_count}"
            )
            experiments.append(
                Experiment(
                    f"parallel-{parallel_count:05d}-workers-{worker_count}",
                    "parallel",
                    build_scalability_command(
                        input_dir,
                        directory,
                        parallel_count,
                        block_size,
                        worker_count,
                        seed,
                    ),
                    str(directory),
                )
            )
    if not skip_pdf:
        directory = output_root / "pdf-scaling"
        command = build_pdf_command(input_dir, directory, seed)
        if command is not None:
            experiments.append(
                Experiment("pdf-scaling", "pdf", command, str(directory))
            )
    if not skip_visual:
        directory = output_root / "visual-checks"
        visual = (
            REPOSITORY_ROOT / "tools" / "visual_checks" / "pipeline_functionality.py"
        )
        experiments.append(
            Experiment(
                "visual-checks",
                "visual",
                [
                    sys.executable,
                    str(visual),
                    "--output-parent",
                    str(directory),
                    "--skip-handwriting",
                ],
                str(directory),
            )
        )
    return experiments


# Input: Keine Parameter; liest Host-, Python- und CPU-Metadaten.
# Output: JSON-kompatible Umgebungsbeschreibung fuer Manifest und Summary.
# Die Daten beschreiben die Ausfuehrungsumgebung, ohne Benchmarks zu starten.
def environment_metadata() -> dict[str, object]:
    return {
        "host": platform.node(),
        "os": platform.platform(),
        "python": sys.version,
        "python_executable": sys.executable,
        "cpu_logical_count": os.cpu_count(),
        "processor": platform.processor(),
    }


# Input: Ein Experiment und ein neuer Suite-Ordner.
# Output: Statusdaten inklusive Start, Ende, Dauer, Returncode und Fehler.
# Der Kindprozess wird ohne Shell mit Argumentliste ausgefuehrt; bei Fehlern
# bleiben alle bereits geschriebenen Benchmarkdateien erhalten.
def run_experiment(experiment: Experiment, repository_root: Path) -> dict[str, object]:
    started = datetime.now(UTC)
    print(f"\n=== {experiment.name} ===")
    print("$ " + " ".join(experiment.command))
    completed = subprocess.run(experiment.command, cwd=repository_root, check=False)
    ended = datetime.now(UTC)
    duration = (ended - started).total_seconds()
    return {
        **asdict(experiment),
        "start": started.isoformat(),
        "end": ended.isoformat(),
        "duration_seconds": duration,
        "returncode": completed.returncode,
        "status": "completed" if completed.returncode == 0 else "failed",
        "error": None
        if completed.returncode == 0
        else f"returncode={completed.returncode}",
    }


# Input: Geparste Suite-Optionen.
# Output: Prozess-Rueckgabecode; Manifest und Summary werden fortlaufend geschrieben.
# Jeder Experimentstatus wird unmittelbar nach dem Kindprozess persistiert.
def run_suite(args: argparse.Namespace) -> int:
    input_dir = args.input_dir.expanduser().resolve()
    if not input_dir.is_dir():
        raise FileNotFoundError(f"Eingabeordner nicht gefunden: {input_dir}")
    output_parent = (
        args.output_root.expanduser().resolve()
        if args.output_root
        else REPOSITORY_ROOT / "thesis-results" / "benchmarks"
    )
    if args.output_root:
        if output_parent.exists():
            raise FileExistsError(
                f"Expliziter output-root existiert bereits: {output_parent}"
            )
        output_root = output_parent
        output_root.mkdir(parents=True, exist_ok=False)
    else:
        output_root = create_output_root(output_parent)
    plan = build_plan(
        input_dir,
        output_root,
        args.counts,
        args.parallel_count,
        args.workers,
        args.block_size,
        args.seed,
        args.skip_parallel,
        args.skip_pdf,
        args.skip_visual,
        args.allow_custom,
    )
    started = datetime.now(UTC)
    manifest: dict[str, object] = {
        "suite": "pc-runtime",
        "status": "running",
        "start": started.isoformat(),
        "configuration": vars(args),
        "environment": environment_metadata(),
        "planned_experiments": [asdict(experiment) for experiment in plan],
    }
    write_json_atomic(output_root / "suite-manifest.json", _jsonable(manifest))
    results: list[dict[str, object]] = []
    interrupted = False
    for experiment in plan:
        try:
            result = run_experiment(experiment, REPOSITORY_ROOT)
        except KeyboardInterrupt:
            result = {
                **asdict(experiment),
                "status": "aborted",
                "error": "KeyboardInterrupt",
            }
            interrupted = True
        except OSError as exc:
            result = {**asdict(experiment), "status": "failed", "error": str(exc)}
        results.append(result)
        manifest["experiments"] = results
        write_json_atomic(output_root / "suite-manifest.json", _jsonable(manifest))
        if interrupted or (result["status"] == "failed" and not args.continue_on_error):
            break
    ended = datetime.now(UTC)
    all_completed = len(results) == len(plan) and all(
        result["status"] == "completed" for result in results
    )
    status = "completed" if all_completed else "aborted" if interrupted else "failed"
    summary = {
        "suite": "pc-runtime",
        "status": status,
        "start": started.isoformat(),
        "end": ended.isoformat(),
        "duration_seconds": (ended - started).total_seconds(),
        "planned_experiment_count": len(plan),
        "executed_experiment_count": len(results),
        "environment": environment_metadata(),
        "experiments": results,
    }
    manifest.update({"status": status, "end": ended.isoformat(), "summary": summary})
    write_json_atomic(output_root / "suite-manifest.json", _jsonable(manifest))
    write_json_atomic(output_root / "suite-summary.json", _jsonable(summary))
    print(f"\nSuite {status}: {output_root}")
    return 0 if status == "completed" else 130 if status == "aborted" else 1


# Input: Daten mit Path-/Namespace-Werten.
# Output: JSON-serialisierbare Datenstruktur fuer Manifestdateien.
# Pfade und CLI-Namespaces werden rekursiv normalisiert.
def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


# Input: Keine Parameter; liest und validiert CLI-Optionen.
# Output: Geparste Optionen fuer `run_suite`.
# Die Defaults beschraenken die PC-Reihe auf die abgestimmten sechs Counts.
def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sichere PC-Laufzeitsuite fuer Thesis-Benchmarks."
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=REPOSITORY_ROOT / "DicomData",
        help="Eingabeordner (Standard: DicomData).",
    )
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--counts", type=parse_counts, default=DEFAULT_COUNTS)
    parser.add_argument("--parallel-count", type=int, default=10_000)
    parser.add_argument("--workers", type=parse_workers, default=DEFAULT_WORKERS)
    parser.add_argument("--block-size", type=int, default=1_000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--skip-parallel", action="store_true")
    pdf_group = parser.add_mutually_exclusive_group()
    pdf_group.add_argument(
        "--skip-pdf",
        action="store_true",
        dest="skip_pdf",
        default=True,
        help="PDF-Benchmark ueberspringen (Standard).",
    )
    pdf_group.add_argument(
        "--run-pdf",
        action="store_false",
        dest="skip_pdf",
        help="PDF-Benchmark explizit einplanen.",
    )
    visual_group = parser.add_mutually_exclusive_group()
    visual_group.add_argument(
        "--skip-visual",
        action="store_true",
        dest="skip_visual",
        default=True,
        help="Visual-Checks ueberspringen (Standard).",
    )
    visual_group.add_argument(
        "--run-visual",
        action="store_false",
        dest="skip_visual",
        help="Visual-Checks zusaetzlich ausfuehren.",
    )
    parser.add_argument("--continue-on-error", action="store_true")
    parser.add_argument(
        "--allow-custom",
        action="store_true",
        help="Abweichende, weiterhin auf 25000 begrenzte Reihen erlauben.",
    )
    return parser.parse_args()


# Input: Keine Parameter; startet die Suite aus der Shell.
# Output: Keine Rueckgabe; beendet den Prozess mit dem Suite-Rueckgabecode.
# Erwartete Konfigurations- und Ausfuehrungsfehler werden klar auf stderr gemeldet.
def main() -> None:
    try:
        raise SystemExit(run_suite(parse_arguments()))
    except (FileExistsError, FileNotFoundError, ValueError) as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
