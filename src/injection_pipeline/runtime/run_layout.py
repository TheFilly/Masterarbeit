"""Run identifier and output path construction."""

import re
from datetime import datetime
from pathlib import Path

_SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


# Input: Laufparameter wie `filetype`, Zeitstempel, Seed und Renderoptionen.
# Output: Stabiler Run-Identifier fuer Ausgabeordner und Manifest.
# Die Funktion codiert die wichtigsten Reproduzierbarkeitsparameter einschliesslich
# der sichtbaren Label- und Handwriting-Optionen in einen menschenlesbaren Namen.
def build_run_id(
    *,
    filetype: str,
    run_timestamp: datetime,
    seed: int,
    rotation_degrees: int,
    placement_mode: str,
    font_size_pct: int,
    font_family: str,
    text_background: str | None,
    show_label_boxes: str = "n",
    handwriting_ink_color: str = "auto",
    handwriting_contrast_mode: str = "none",
) -> str:
    text_background_label = text_background or "none"
    return (
        f"{filetype}-{run_timestamp.strftime('%d%m%Y')}-{run_timestamp.strftime('%H%M')}"
        f"-seed{seed:04d}-angle{rotation_degrees:03d}-{placement_mode}"
        f"-fs{font_size_pct}-{font_family}-{text_background_label}"
        f"-labels{show_label_boxes}-ink{handwriting_ink_color}"
        f"-contrast{handwriting_contrast_mode}"
    )


# Input: `output_root`, `run_id`, `source_stem` und `output_suffix`.
# Output: Pfad-Mapping fuer Ausgabe, Ground Truth, Manifest und Previews.
# Die Funktion erzeugt nur Pfadobjekte; Verzeichnisse werden hier noch nicht
# auf dem Dateisystem angelegt.
def build_output_paths(
    output_root: Path,
    run_id: str,
    source_stem: str,
    output_suffix: str,
) -> dict[str, Path]:
    if not _SAFE_RUN_ID.fullmatch(run_id):
        raise ValueError(f"run_id must be a safe single path segment: {run_id!r}")
    if output_root.exists() and not output_root.is_dir():
        raise ValueError(f"output root must be a directory: {output_root}")
    run_dir = output_root / run_id
    return {
        "run_dir": run_dir,
        "output_file": run_dir / f"{source_stem}_injected{output_suffix}",
        "output_json": run_dir / "ground_truth.json",
        "output_manifest": run_dir / "run_manifest.json",
        "preview_file": run_dir / "preview.png",
        "annotated_preview_file": run_dir / "preview_annotated.png",
    }


# Input: Geplanter Ausgabeordner.
# Output: Keine Rueckgabe; wirft bei belegtem Run-Ordner.
# Die Funktion reserviert keine Dateien, verhindert aber, dass ein neuer Lauf
# still in ein bestehendes Run-Bundle schreibt.
def ensure_run_directory_available(run_dir: Path) -> None:
    if run_dir.exists():
        raise ValueError(f"run directory already exists: {run_dir}")
