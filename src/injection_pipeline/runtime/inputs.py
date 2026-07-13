"""Input discovery and document type detection for pipeline runs."""

import random
import re
from pathlib import Path

from injection_pipeline.loaders.registry import resolve
from injection_pipeline.runtime.seeding import derive_seed

DEFAULT_DICOM_DIR = Path("DycomData/Dicom-Files")
DEFAULT_IMAGE_DIR = Path("DycomData/images")
DEFAULT_INPUT_EXTENSIONS: tuple[str, ...] = (".dcm", ".jpg", ".jpeg")


# Input: `dicom_dir` und `image_dir` mit Prototype-Quellordnern.
# Output: Sortierte Liste erlaubter Default-Eingabedateien.
# Die Funktion sammelt direkt abgelegte DICOM- und JPG/JPEG-Dateien und
# ignoriert andere Formate.
def collect_default_input_candidates(
    dicom_dir: Path = DEFAULT_DICOM_DIR,
    image_dir: Path = DEFAULT_IMAGE_DIR,
) -> list[Path]:
    candidates: list[Path] = []
    for directory in (dicom_dir, image_dir):
        if not directory.exists():
            continue
        candidates.extend(
            path
            for path in directory.iterdir()
            if path.is_file() and path.suffix.lower() in DEFAULT_INPUT_EXTENSIONS
        )
    return sorted(candidates, key=lambda path: str(path).lower())


# Input: `candidates` mit moeglichen Default-Eingabedateien und `seed`.
# Output: Reproduzierbar ausgewaehlter Pfad.
# Die Funktion sortiert die Kandidaten vor der Auswahl und nutzt den benannten
# `input_selection`-Stream; fehlende Kandidaten bleiben ein ValueError.
def select_seeded_default_input(candidates: list[Path], seed: int) -> Path:
    if not candidates:
        raise ValueError(
            "No default input files found in "
            f"{DEFAULT_DICOM_DIR} or {DEFAULT_IMAGE_DIR}."
        )
    sorted_candidates = sorted(candidates, key=lambda path: str(path).lower())
    rng = random.Random(derive_seed(seed, "input_selection"))
    return rng.choice(sorted_candidates)


# Input: `seed` fuer den benannten Input-Auswahlstrom.
# Output: Reproduzierbar ausgewaehlter Default-Eingabepfad.
# Die Funktion verbindet Kandidatensammlung und seeded Auswahl fuer die
# Convenience-Auswahl ohne explizites `--input`.
def select_default_input_path(seed: int) -> Path:
    return select_seeded_default_input(collect_default_input_candidates(), seed)


# Input: `raw_input` mit optionalem CLI-Pfad und `seed` fuer Auto-Auswahl.
# Output: Eingabepfad und Flag, ob er automatisch gewaehlt wurde.
# Die Funktion priorisiert explizite Nutzereingaben und nutzt nur ohne Pfad den
# seeded Prototype-Default.
def resolve_input_path(raw_input: str | None, seed: int) -> tuple[Path, bool]:
    if raw_input:
        return Path(raw_input), False
    return select_default_input_path(seed), True


# Input: `input_path` mit Quelleingabepfad.
# Output: Abgeleiteter Beispieltyp als kurzer String.
# Die Funktion nutzt den naechsten aussagekraeftigen Ordnernamen und faellt
# sonst auf `dicom` zurueck.
def derive_example_type(input_path: Path) -> str:
    for part in reversed(input_path.parts[:-1]):
        normalized = re.sub(r"[^a-z0-9]+", "-", part.lower()).strip("-")
        if normalized and normalized not in {"original-data", "anonymization"}:
            return normalized
    return "dicom"


# Input: `input_path` mit Quelleingabepfad.
# Output: Dokumenttyp der registrierten Adapter.
# Die Funktion delegiert die Formatpruefung an die Adapter-Registry und behaelt
# die bisherige ValueError-Meldung fuer unbekannte Formate.
def detect_input_type(input_path: Path) -> str:
    loader, _writer = resolve(input_path)
    return loader.format_id
