"""Erzeuge reproduzierbare Diagramme aus den Benchmark-CSV-Dateien."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT = REPOSITORY_ROOT / "output" / "thesis-results" / "plots"


# Input: CSV-Pfad mit numerischen Messwerten.
# Output: Liste von Wörterbuchzeilen mit numerisch konvertierten Werten.
# Die Funktion verwendet nur persistierte Rohdaten und ergänzt keine Messwerte.
def read_rows(path: Path) -> list[dict[str, float]]:
    rows: list[dict[str, float]] = []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            numeric_row: dict[str, float] = {}
            for key, value in row.items():
                if value is None or value == "":
                    continue
                try:
                    numeric_row[key] = float(value)
                except ValueError:
                    continue
            rows.append(numeric_row)
    return rows


# Input: Skalierbarkeits-CSV und Zielordner.
# Output: Keine Rückgabe; schreibt Laufzeit-, Durchsatz- und Speicherdiagramme.
# Die Abbildung nutzt jeden gemessenen Block und macht keine statistische Glättung.
def plot_scalability(path: Path, output_dir: Path) -> None:
    rows = read_rows(path)
    completed = [row["documents_completed"] for row in rows]
    elapsed = [
        row.get("cumulative_elapsed_seconds", row["elapsed_seconds"]) for row in rows
    ]
    throughput = [
        row.get(
            "cumulative_throughput_documents_per_second",
            row["throughput_documents_per_second"],
        )
        for row in rows
    ]
    memory = [row["peak_memory_bytes"] / 1024**2 for row in rows]

    figure, axes = plt.subplots(3, 1, figsize=(8, 12), constrained_layout=True)
    axes[0].plot(completed, elapsed, marker="o")
    axes[0].set(xlabel="Abgeschlossene Dokumente", ylabel="Laufzeit (s)")
    axes[0].grid(True, alpha=0.3)
    axes[1].plot(completed, throughput, marker="o")
    axes[1].set(xlabel="Abgeschlossene Dokumente", ylabel="Durchsatz (Dokumente/s)")
    axes[1].grid(True, alpha=0.3)
    axes[2].plot(completed, memory, marker="o")
    axes[2].set(xlabel="Abgeschlossene Dokumente", ylabel="Peak-Speicher (MiB)")
    axes[2].grid(True, alpha=0.3)
    output_dir.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_dir / "scalability_overview.png", dpi=160)
    plt.close(figure)


# Input: PDF-CSV und Zielordner.
# Output: Keine Rückgabe; schreibt Laufzeitkurven und Laufzeit-pro-Bild-Diagramme.
# Wiederholungen werden als Einzelpunkte und je Bildanzahl gemittelt dargestellt.
def plot_pdf_scaling(path: Path, output_dir: Path) -> None:
    rows = read_rows(path)
    grouped: dict[float, list[dict[str, float]]] = defaultdict(list)
    for row in rows:
        grouped[row["image_count"]].append(row)
    counts = sorted(grouped)
    mean_elapsed = [
        sum(row["elapsed_seconds"] for row in grouped[count]) / len(grouped[count])
        for count in counts
    ]
    mean_per_image = [
        sum(row["elapsed_per_image_seconds"] for row in grouped[count])
        / len(grouped[count])
        for count in counts
    ]

    figure, axes = plt.subplots(2, 1, figsize=(8, 8), constrained_layout=True)
    for count in counts:
        axes[0].scatter(
            [count] * len(grouped[count]),
            [row["elapsed_seconds"] for row in grouped[count]],
            alpha=0.7,
        )
    axes[0].plot(counts, mean_elapsed, marker="o", label="Mittelwert")
    axes[0].set(xlabel="Bilder pro PDF", ylabel="Laufzeit (s)")
    axes[0].legend()
    axes[0].grid(True, alpha=0.3)
    axes[1].plot(counts, mean_per_image, marker="o")
    axes[1].set(xlabel="Bilder pro PDF", ylabel="Laufzeit pro Bild (s)")
    axes[1].grid(True, alpha=0.3)
    output_dir.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_dir / "pdf_scaling.png", dpi=160)
    plt.close(figure)


# Input: CSV-Optionen und Ausgabeordner aus der Kommandozeile.
# Output: Keine Rückgabe; erzeugt die angeforderten Ergebnisdiagramme.
# Nicht angegebene CSV-Dateien werden übersprungen, damit einzelne Benchmarks separat
# ausgewertet werden können.
def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmarkdiagramme für die Thesis.")
    parser.add_argument("--scalability-csv", type=Path)
    parser.add_argument("--pdf-csv", type=Path)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


# Input: Keine direkten Parameter; Optionen werden aus der Kommandozeile gelesen.
# Output: Keine Rückgabe; erzeugt die verfügbaren Diagramme.
def main() -> None:
    args = parse_arguments()
    if args.scalability_csv:
        plot_scalability(args.scalability_csv, args.output_dir)
    if args.pdf_csv:
        plot_pdf_scaling(args.pdf_csv, args.output_dir)
    if not args.scalability_csv and not args.pdf_csv:
        raise SystemExit("Mindestens --scalability-csv oder --pdf-csv angeben.")


if __name__ == "__main__":
    main()
