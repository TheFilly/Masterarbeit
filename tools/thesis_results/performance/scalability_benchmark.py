"""Messung der sequentiellen und optional parallelen Dokumentverarbeitung."""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from collections.abc import Iterator
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import partial
from pathlib import Path

import injection_pipeline.api as pipeline_api
from injection_pipeline import inject_function

from .common import (
    environment_metadata,
    iter_blocks,
    measure_call,
    peak_memory_bytes,
    write_csv,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT = REPOSITORY_ROOT / "output" / "thesis-results" / "scalability"
DEFAULT_TIMESTAMP = datetime(2026, 1, 1, 0, 0, 0)
CSV_FIELDS = [
    "block_index",
    "documents_in_block",
    "documents_completed",
    "elapsed_seconds",
    "elapsed_per_document_seconds",
    "cumulative_elapsed_seconds",
    "cumulative_throughput_documents_per_second",
    "throughput_documents_per_second",
    "peak_memory_bytes",
    "mode",
    "workers",
    "seed",
]


@dataclass(frozen=True)
class DocumentJob:
    """Reproduzierbarer Auftrag für eine einzelne Dokumentinjektion."""

    source: Path
    document_type: str
    output_dir: Path
    seed: int
    run_timestamp: datetime


# Input: Ein Pfad mit DICOM-/JPG-Dateien oder ein übergeordneter Datenordner.
# Output: Sortierte Liste unterstützter Eingabedateien.
# Die Auswahl ist deterministisch und berücksichtigt keine bereits erzeugten
# Ausgabedateien.
def discover_sources(input_dir: Path) -> list[Path]:
    if not input_dir.is_dir():
        raise FileNotFoundError(f"Eingabeordner nicht gefunden: {input_dir}")
    sources = sorted(
        path
        for path in input_dir.rglob("*")
        if path.is_file()
        and path.suffix.casefold() in {".dcm", ".jpg", ".jpeg"}
        and _is_supported_source(path)
    )
    if not sources:
        raise FileNotFoundError(
            f"Keine .dcm-, .jpg- oder .jpeg-Dateien unter {input_dir} gefunden."
        )
    return sources


# Input: Kandidat mit `.dcm`-, `.jpg`- oder `.jpeg`-Endung.
# Output: `True`, wenn die Pipeline den Kandidaten laut aktuellem Vertrag verarbeitet.
# Nicht unterstuetzte DICOMs werden vor einem langen Benchmark explizit
# ausgeschlossen; JPG/JPEG werden direkt als unterstuetzt behandelt.
def _is_supported_source(path: Path) -> bool:
    if path.suffix.casefold() != ".dcm":
        return True
    try:
        import pydicom

        dataset = pydicom.dcmread(path, stop_before_pixels=True)
    except (OSError, ValueError, pydicom.errors.InvalidDicomError):
        return False
    photometric = str(getattr(dataset, "PhotometricInterpretation", "")).upper()
    samples = int(getattr(dataset, "SamplesPerPixel", 1))
    return (
        int(getattr(dataset, "BitsAllocated", 0)) == 8
        and photometric in {"MONOCHROME2", "RGB", "YBR_FULL_422"}
        and (
            (photometric in {"RGB", "YBR_FULL_422"} and samples == 3)
            or (photometric == "MONOCHROME2" and samples == 1)
        )
    )


# Input: Unterstützte Quelldateien und ein Cache-Verzeichnis.
# Output: Kopien mit kurzen, deterministischen Dateinamen.
# Die Kopien vermeiden unter Windows zu lange Ausgabepfade der Pipeline; das
# Kopieren erfolgt vor der Zeitmessung und wird nach dem Benchmark entfernt.
def _stage_sources(sources: list[Path], cache_dir: Path) -> list[Path]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    staged: list[Path] = []
    for index, source in enumerate(sources):
        target = cache_dir / f"source-{index:06d}{source.suffix.lower()}"
        shutil.copy2(source, target)
        staged.append(target)
    return staged


# Input: Sortierte Quellen und gewünschte Dokumentanzahl.
# Output: Iterator mit deterministisch wiederverwendeten Quellen und Dokumentmetadaten.
# Für große Pilotläufe werden lokale Testdaten zyklisch verwendet; die Messung bleibt
# dadurch von einer exakt gleich großen Eingabedatensammlung unabhängig.
def build_jobs(
    sources: list[Path],
    count: int,
    output_dir: Path,
    seed: int,
    run_timestamp: datetime,
) -> Iterator[DocumentJob]:
    if count < 1:
        raise ValueError("count muss mindestens 1 sein.")
    for index in range(count):
        source = sources[index % len(sources)]
        document_type = "dcm" if source.suffix.casefold() == ".dcm" else "jpg"
        yield DocumentJob(
            source=source,
            document_type=document_type,
            output_dir=output_dir,
            seed=seed + index,
            run_timestamp=run_timestamp + timedelta(seconds=index),
        )


# Input: Ein vollständig definierter Dokumentauftrag.
# Output: Peak-Speicher des abgeschlossenen Auftrags in Bytes.
# Die Standardparameter sind absichtlich fest und erlauben den Vergleich zwischen
# sequentieller und paralleler Verarbeitung ohne Änderung des Produktionspfads.
def process_job(job: DocumentJob) -> int:
    original_output_dir = pipeline_api.__dict__["DEFAULT_OUTPUT_DIR"]
    pipeline_api.__dict__["DEFAULT_OUTPUT_DIR"] = job.output_dir
    job.output_dir.mkdir(parents=True, exist_ok=True)
    try:
        inject_function(
            category="ThesisBenchmark",
            value=f"SYNTH-{job.seed:08d}",
            prefix="ID: ",
            suffix="",
            handwritten=False,
            documentType=job.document_type,
            input_path=job.source,
            seed=job.seed,
            rotation_degrees=0,
            run_timestamp=job.run_timestamp,
        )
        return peak_memory_bytes()
    finally:
        pipeline_api.__dict__["DEFAULT_OUTPUT_DIR"] = original_output_dir


# Input: Auftragsblock und gewünschte Workeranzahl.
# Output: Höchster gemeldeter Peak-Speicher eines Auftrags in Bytes.
# Bei einem Worker läuft die Verarbeitung sequentiell, bei mehreren Workern
# dokumentweise über ProcessPoolExecutor.
def process_block(jobs: list[DocumentJob], workers: int) -> int:
    if workers < 1:
        raise ValueError("workers muss mindestens 1 sein.")
    if workers == 1:
        return max((process_job(job) for job in jobs), default=0)
    with ProcessPoolExecutor(max_workers=workers) as executor:
        return max(executor.map(process_job, jobs), default=0)


# Input: Parser mit allen reproduzierbaren Benchmarkoptionen.
# Output: Geparste Kommandozeilenoptionen.
# Die Defaults bilden einen kleinen Pilotlauf ab; größere Stufen werden
# explizit gewählt.
def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Skalierbarkeitsbenchmark für InjectionPipeline."
    )
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--count", type=int, default=10_000)
    parser.add_argument("--block-size", type=int, default=1_000)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--run-timestamp",
        type=datetime.fromisoformat,
        default=DEFAULT_TIMESTAMP,
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--keep-artifacts",
        action="store_true",
        help=(
            "Erzeugte DICOM/JPG-Artefakte behalten; standardmäßig werden sie "
            "blockweise entfernt."
        ),
    )
    return parser.parse_args()


# Input: Geparste Benchmarkoptionen.
# Output: Keine Rückgabe; schreibt CSV-/JSON-Zwischenstände und die Meldung.
# Jeder Block wird separat gemessen und sofort persistiert, damit ein langer Lauf
# nach einem Abbruch anhand des letzten Checkpoints nachvollziehbar bleibt.
# Input: Geparste Benchmarkoptionen.
# Output: Keine Rueckgabe; der Staging-Cache wird unabhaengig vom Ergebnis entfernt.
# Die Huelle stellt sicher, dass auch bei einem Fehler keine Eingabekopien im
# Ausgabeordner zurueckbleiben.
def run_benchmark(args: argparse.Namespace) -> None:
    args.output_dir.mkdir(parents=True, exist_ok=True)
    source_cache = Path(
        tempfile.mkdtemp(prefix=".sources-", dir=args.output_dir)
    )
    args._source_cache = source_cache
    try:
        _run_benchmark_impl(args)
    finally:
        shutil.rmtree(source_cache, ignore_errors=True)


# Input: Geparste Benchmarkoptionen.
# Output: Keine Rueckgabe; schreibt CSV-/JSON-Zwischenstaende und die Meldung.
# Jeder Block wird separat gemessen und sofort persistiert, damit ein langer Lauf
# nach einem Abbruch anhand des letzten Checkpoints nachvollziehbar bleibt.
def _run_benchmark_impl(args: argparse.Namespace) -> None:
    if args.block_size < 1:
        raise ValueError("block-size muss mindestens 1 sein.")
    sources = discover_sources(args.input_dir)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    artifact_root = args.output_dir / "artifacts"
    artifact_root.mkdir(parents=True, exist_ok=True)
    source_cache = Path(args._source_cache)
    staged_sources = _stage_sources(sources, source_cache)
    jobs = build_jobs(
        staged_sources,
        args.count,
        artifact_root,
        args.seed,
        args.run_timestamp,
    )
    rows: list[dict[str, object]] = []
    completed = 0
    cumulative_elapsed = 0.0
    for block_index, jobs_block in enumerate(
        iter_blocks(jobs, args.block_size), start=1
    ):
        block_dir = artifact_root / f"block-{block_index:06d}"
        block_dir.mkdir(parents=True, exist_ok=True)
        block_jobs = [
            DocumentJob(
                source=job.source,
                document_type=job.document_type,
                output_dir=block_dir,
                seed=job.seed,
                run_timestamp=job.run_timestamp,
            )
            for job in jobs_block
        ]
        memory_before = peak_memory_bytes()
        worker_peak, timing = measure_call(
            partial(process_block, block_jobs, args.workers)
        )
        completed += len(block_jobs)
        cumulative_elapsed += timing.elapsed_seconds
        elapsed_per_document = timing.elapsed_seconds / len(block_jobs)
        row = {
            "block_index": block_index,
            "documents_in_block": len(block_jobs),
            "documents_completed": completed,
            "elapsed_seconds": timing.elapsed_seconds,
            "elapsed_per_document_seconds": elapsed_per_document,
            "cumulative_elapsed_seconds": cumulative_elapsed,
            "cumulative_throughput_documents_per_second": completed
            / cumulative_elapsed,
            "throughput_documents_per_second": len(block_jobs) / timing.elapsed_seconds,
            "peak_memory_bytes": max(
                timing.peak_memory_bytes,
                memory_before,
                worker_peak,
            ),
            "mode": "sequential" if args.workers == 1 else "parallel",
            "workers": args.workers,
            "seed": args.seed,
        }
        rows.append(row)
        write_csv(args.output_dir / "measurements.csv", rows, CSV_FIELDS)
        checkpoint = {
            "completed": completed,
            "requested": args.count,
            "block_index": block_index,
            "block_size": args.block_size,
            "workers": args.workers,
            "seed": args.seed,
            "run_timestamp": args.run_timestamp.isoformat(),
            "source_count": len(sources),
            "environment": environment_metadata(),
        }
        (args.output_dir / "checkpoint.json").write_text(
            json.dumps(checkpoint, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(row, ensure_ascii=False))
        if not args.keep_artifacts:
            shutil.rmtree(block_dir)
    print(f"Benchmark abgeschlossen: {completed} Dokumente")


# Input: Keine direkten Parameter; Optionen werden aus der Kommandozeile gelesen.
# Output: Keine Rückgabe; startet den reproduzierbaren Benchmark.
# Der Einstiegspunkt ist direkt mit `uv run python` ausführbar und verändert keine
# Produktionskonfiguration der Pipeline.
def main() -> None:
    run_benchmark(parse_arguments())


if __name__ == "__main__":
    main()
