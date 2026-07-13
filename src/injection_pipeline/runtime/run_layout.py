"""Run identifier and output path construction."""

from datetime import datetime
from pathlib import Path


# Input: Laufparameter wie `filetype`, Zeitstempel, Seed und Renderoptionen.
# Output: Stabiler Run-Identifier fuer Ausgabeordner und Manifest.
# Die Funktion codiert die wichtigsten Reproduzierbarkeitsparameter in einen
# menschenlesbaren Namen.
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
) -> str:
    text_background_label = text_background or "none"
    return (
        f"{filetype}-{run_timestamp.strftime('%d%m%Y')}-{run_timestamp.strftime('%H%M')}"
        f"-seed{seed:04d}-angle{rotation_degrees:03d}-{placement_mode}"
        f"-fs{font_size_pct}-{font_family}-{text_background_label}"
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
    run_dir = output_root / run_id
    return {
        "run_dir": run_dir,
        "output_file": run_dir / f"{source_stem}_injected{output_suffix}",
        "output_json": run_dir / "ground_truth.json",
        "output_manifest": run_dir / "run_manifest.json",
        "preview_file": run_dir / "preview.png",
        "annotated_preview_file": run_dir / "preview_annotated.png",
    }
