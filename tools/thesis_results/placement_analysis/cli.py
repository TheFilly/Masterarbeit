"""Argumentparser für die Platzierungsanalyse."""

from __future__ import annotations

import argparse
from pathlib import Path

from .analysis import analyze_paths


# Input: Kommandozeilenargumente oder `None` für `sys.argv`.
# Output: Exit-Code 0 nach erfolgreicher Auswertung.
# Das Kommando durchsucht Verzeichnisse rekursiv und schreibt einen neuen Analyseordner.
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", required=True, type=Path, help="Datei oder Verzeichnis"
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("thesis-results/validation")
    )
    parser.add_argument("--analysis-name", default="placement-analysis")
    parser.add_argument("--width", type=float)
    parser.add_argument("--height", type=float)
    parser.add_argument("--bins", type=int, default=10)
    args = parser.parse_args(argv)
    if (args.width is None) != (args.height is None):
        parser.error("--width und --height müssen gemeinsam gesetzt werden.")
    result = analyze_paths(
        args.input,
        args.output_dir,
        args.analysis_name,
        args.bins,
        args.width,
        args.height,
    )
    print(f"Platzierungsanalyse nach {result} geschrieben.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
