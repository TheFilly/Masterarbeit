"""Font resolution helpers for pixel injection."""

from collections.abc import Iterable
from pathlib import Path

from PIL import ImageFont

_DEFAULT_FONT_SIZE_PX: int = 18
_FontPathCandidate = str | Path
_FontPathConfig = _FontPathCandidate | Iterable[_FontPathCandidate]
_FONT_PATHS: dict[str, _FontPathConfig] = {
    "arial": (
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
        Path("/Library/Fonts/Arial.ttf"),
        Path("/usr/share/fonts/truetype/msttcorefonts/Arial.ttf"),
        Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"),
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
    ),
    "calibri": (
        Path("C:/Windows/Fonts/calibri.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
        Path("/usr/share/fonts/truetype/crosextra/Carlito-Regular.ttf"),
    ),
    "tahoma": (
        Path("C:/Windows/Fonts/tahoma.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ),
    "consolas": (
        Path("C:/Windows/Fonts/consola.ttf"),
        Path("/System/Library/Fonts/Menlo.ttc"),
        Path("/System/Library/Fonts/Supplemental/Courier New.ttf"),
        Path("/usr/share/fonts/truetype/liberation2/LiberationMono-Regular.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"),
    ),
}


# Input: `font_size_pct` mit relativer Prototyp-Schriftgroesse.
# Output: Absolute Schriftgroesse in Pixeln.
# Die Funktion skaliert vom festen Prototyp-Basiswert und lehnt Werte kleiner
# eins ab.
def _resolve_font_size_px(font_size_pct: int) -> int:
    if font_size_pct < 1:
        raise ValueError("font_size_pct must be >= 1")
    return max(1, round(_DEFAULT_FONT_SIZE_PX * font_size_pct / 100))


# Input: `font_paths` mit einem Pfad oder mehreren Fallback-Kandidaten.
# Output: Tuple normalisierter `Path`-Objekte.
# Die Funktion haelt alte Tests mit einzelnen String-Pfaden kompatibel und
# vereinheitlicht die plattformabhaengigen Font-Kandidaten.
def _iter_font_paths(font_paths: _FontPathConfig) -> tuple[Path, ...]:
    if isinstance(font_paths, (str, Path)):
        return (Path(font_paths),)
    return tuple(Path(font_path) for font_path in font_paths)


# Input: `font_family` als konfigurierter Font-Key und `font_size_px`.
# Output: Geladener Pillow-Font.
# Die Funktion prueft plattformabhaengige Kandidaten nacheinander und meldet
# alle versuchten Pfade, wenn kein Font geladen werden kann.
# `layout_engine=BASIC` wird erzwungen, weil Pillow sonst RAQM waehlt, sobald
# die installierte Wheel libraqm mitbringt - das aendert Kerning/Shaping und
# damit Bounding-Boxes je nach Plattform-Wheel, nicht je nach Pillow-Version.
def load_default_font(
    font_family: str = "arial",
    font_size_px: int = _DEFAULT_FONT_SIZE_PX,
) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    font_paths = _FONT_PATHS.get(font_family)
    if font_paths is None:
        raise ValueError(
            f"font_family must be one of {tuple(_FONT_PATHS)}, got {font_family!r}."
        )
    attempted_paths: list[str] = []
    for font_path in _iter_font_paths(font_paths):
        attempted_paths.append(str(font_path))
        if not font_path.exists():
            continue
        try:
            return ImageFont.truetype(
                font_path, size=font_size_px, layout_engine=ImageFont.Layout.BASIC
            )
        except OSError:
            continue
    raise RuntimeError(
        f"Configured prototype font {font_family!r} is unavailable. "
        f"Checked: {', '.join(attempted_paths)}."
    )
