"""Miss den PDF-Aufwand in Abhängigkeit von der Bildanzahl."""

from __future__ import annotations

import argparse
import json
from functools import partial
from pathlib import Path

from PIL import Image
from pypdf import PdfReader

from injection_pipeline import make_pdf
from injection_pipeline.models.geometry import ImagePoint, Quad
from injection_pipeline.pdf.models import (
    PdfMakeImageAnnotationInput,
    PdfMakeImageInput,
    PdfMakeTextInput,
)

from .common import environment_metadata, measure_call, peak_memory_bytes, write_csv

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT = REPOSITORY_ROOT / "output" / "thesis-results" / "pdf-scaling"
CSV_FIELDS = [
    "image_count",
    "repetition",
    "elapsed_seconds",
    "elapsed_per_image_seconds",
    "output_size_bytes",
    "page_count",
    "peak_memory_bytes",
    "seed",
]


# Input: Maximale Bildanzahl, die im PDF-Benchmark untersucht werden soll.
# Output: Aufsteigende Zweierpotenzen bis einschließlich maximaler Bildanzahl.
# Die Standardreihe bildet die vereinbarten Fälle 1, 2, 4, 8 und 16 ab.
def image_counts(max_images: int) -> list[int]:
    if max_images < 1:
        raise ValueError("max_images muss mindestens 1 sein.")
    counts: list[int] = []
    count = 1
    while count <= max_images:
        counts.append(count)
        count *= 2
    return counts


# Input: Eine vorhandene Bilddatei und gewünschte Anzahl identischer Bildeinträge.
# Output: Validierte `PdfMakeImageInput`-Liste für `make_pdf`.
# Das identische Wiederverwenden isoliert zunächst den Einfluss der Bildanzahl von
# Bildinhalt und Bildgröße; die Quelle wird nicht verändert.
def build_image_inputs(image: Path, count: int) -> list[PdfMakeImageInput]:
    if not image.is_file():
        raise FileNotFoundError(f"Bildquelle nicht gefunden: {image}")
    if count < 1:
        raise ValueError("count muss mindestens 1 sein.")
    with Image.open(image) as opened:
        width, height = opened.size
    if width < 4 or height < 4:
        raise ValueError("Die Bildquelle muss mindestens 4 × 4 Pixel groß sein.")
    right = max(2.0, min(float(width - 2), width * 0.4))
    bottom = max(2.0, min(float(height - 2), height * 0.4))
    annotation = PdfMakeImageAnnotationInput(
        category="ThesisBenchmark",
        value="SYNTH-IMAGE",
        prefix="ID: ",
        suffix="",
        rendered_text="ID: SYNTH-IMAGE",
        image_corners=Quad(
            [
                ImagePoint(x=2.0, y=2.0),
                ImagePoint(x=right, y=2.0),
                ImagePoint(x=right, y=bottom),
                ImagePoint(x=2.0, y=bottom),
            ]
        ),
    )
    return [
        PdfMakeImageInput(path=image, annotations=[annotation]) for _ in range(count)
    ]


# Input: PDF-Template, identische Bildeinträge, Ausgabeordner und Seed.
# Output: Erzeugte PDF-Artefakte sowie deren Seitenanzahl und Dateigröße.
# Der Aufruf nutzt ausschließlich die bestehende öffentliche PDF-Kompositions-API.
def compose_pdf(
    template: Path,
    image: Path,
    image_count: int,
    output_dir: Path,
    seed: int,
) -> tuple[int, int]:
    artifacts = make_pdf(
        images=build_image_inputs(image, image_count),
        texts=[
            PdfMakeTextInput(
                category="ThesisBenchmark",
                value="SYNTH-PDF",
                prefix="ID: ",
                suffix="",
                handwritten=False,
            )
        ],
        pdf=template,
        output_dir=output_dir,
        seed=seed,
    )
    return len(
        PdfReader(str(artifacts.clean_pdf)).pages
    ), artifacts.clean_pdf.stat().st_size


# Input: Geparste PDF-Benchmarkoptionen.
# Output: Keine Rückgabe; schreibt Rohmessungen und einen reproduzierbaren Checkpoint.
# Jeder Wert erhält einen Warm-up-Lauf und anschließend die vereinbarte Anzahl echter
# Wiederholungen; Ergebnisse werden nach jeder Konfiguration persistiert.
def run_benchmark(args: argparse.Namespace) -> None:
    if args.repetitions < 1:
        raise ValueError("repetitions muss mindestens 1 sein.")
    if not args.template.is_file():
        raise FileNotFoundError(f"PDF-Template nicht gefunden: {args.template}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    completed_configurations: list[int] = []
    for image_count in image_counts(args.max_images):
        warmup_dir = args.output_dir / f"warmup-images-{image_count}"
        compose_pdf(args.template, args.image, image_count, warmup_dir, args.seed)
        for repetition in range(1, args.repetitions + 1):
            output_dir = (
                args.output_dir / f"images-{image_count}" / f"run-{repetition:02d}"
            )
            memory_before = peak_memory_bytes()
            (page_count, output_size), timing = measure_call(
                partial(
                    compose_pdf,
                    args.template,
                    args.image,
                    image_count,
                    output_dir,
                    args.seed + repetition,
                )
            )
            row = {
                "image_count": image_count,
                "repetition": repetition,
                "elapsed_seconds": timing.elapsed_seconds,
                "elapsed_per_image_seconds": timing.elapsed_seconds / image_count,
                "output_size_bytes": output_size,
                "page_count": page_count,
                "peak_memory_bytes": max(timing.peak_memory_bytes, memory_before),
                "seed": args.seed + repetition,
            }
            rows.append(row)
            write_csv(args.output_dir / "measurements.csv", rows, CSV_FIELDS)
            print(json.dumps(row, ensure_ascii=False))
        completed_configurations.append(image_count)
        checkpoint = {
            "template": str(args.template),
            "image": str(args.image),
            "image_counts": image_counts(args.max_images),
            "completed_configurations": completed_configurations,
            "repetitions": args.repetitions,
            "warmup_runs_per_configuration": 1,
            "seed": args.seed,
            "environment": environment_metadata(),
        }
        (args.output_dir / "checkpoint.json").write_text(
            json.dumps(checkpoint, indent=2) + "\n",
            encoding="utf-8",
        )


# Input: Parser mit PDF-Template, Bildquelle und Messparametern.
# Output: Geparste Kommandozeilenoptionen.
# Die Defaults entsprechen dem Pilotdesign und sind ohne Codeänderung anpassbar.
def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="PDF-Benchmark für die Thesis-Ergebnisse."
    )
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--max-images", type=int, default=16)
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


# Input: Keine direkten Parameter; Optionen werden aus der Kommandozeile gelesen.
# Output: Keine Rückgabe; startet den PDF-Benchmark.
# Die Funktion ist direkt mit `uv run python` beziehungsweise als Modul ausführbar.
def main() -> None:
    run_benchmark(parse_arguments())


if __name__ == "__main__":
    main()
