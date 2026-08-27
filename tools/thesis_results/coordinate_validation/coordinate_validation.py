"""Reproduzierbare Auswertung von Ground-Truth-Bounding-Boxes."""

from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, cast

Point = Mapping[str, float] | Sequence[float]


@dataclass(frozen=True)
class BoundingBoxResult:
    """Validierungsergebnis einer Ground-Truth-Bounding-Box."""

    left: float
    top: float
    right: float
    bottom: float
    center_x: float
    center_y: float
    within_bounds: bool
    text_not_clipped: bool
    issues: str


@dataclass(frozen=True)
class PixelComparisonResult:
    """Vergleich zwischen Ground Truth und erkannter Pixel-Bounding-Box."""

    ground_truth_left: float
    ground_truth_top: float
    ground_truth_right: float
    ground_truth_bottom: float
    actual_left: int | None
    actual_top: int | None
    actual_right: int | None
    actual_bottom: int | None
    clipping_detected: bool
    center_error_px: float | None
    iou: float
    within_tolerance: bool
    mask_clipped: bool
    roi_left: int
    roi_top: int
    roi_right: int
    roi_bottom: int


@dataclass(frozen=True)
class PdfRenderResult:
    """Metadaten eines mit `pdftoppm` gerenderten PDF-Seitenbildes."""

    renderer: str
    page_index: int
    dpi: int
    output_png: str
    renderer_version: str
    render_command: list[str]


# Input: `mask` als rechteckige Matrix und eine halb-offene ROI in Pixeln.
# Output: Neue Maske mit Vordergrund ausschließlich innerhalb der ROI.
# Die Funktion begrenzt die Textsuche auf die aus der Ground Truth abgeleitete
# Region und verhindert dadurch Treffer durch medizinische Bildinhalte daneben.
def _mask_in_roi(
    mask: Sequence[Sequence[bool | int]],
    roi: tuple[int, int, int, int],
) -> list[list[bool]]:
    left, top, right, bottom = roi
    return [
        [
            bool(value) and left <= x < right and top <= y < bottom
            for x, value in enumerate(row)
        ]
        for y, row in enumerate(mask)
    ]


# Input: Ground-Truth-Box, Rastermaske, Bildabmessungen und Toleranz.
# Output: Pixel-Bounding-Box mit IoU, Mittelpunktfehler, ROI- und Clippingbefund.
# `mask_clipped` meldet ausdrücklich eine tatsächliche Maske, die kleiner als
# die erwartete Ground-Truth-Box ist.
def _compare_bbox_in_roi(
    corners: Sequence[Point],
    rendered_mask: Sequence[Sequence[bool | int]],
    width: float,
    height: float,
    tolerance: float,
    roi_padding: int,
) -> PixelComparisonResult:
    gt_left, gt_top, gt_right, gt_bottom = bounding_box_from_corners(corners)
    roi = (
        max(0, math.floor(gt_left) - roi_padding),
        max(0, math.floor(gt_top) - roi_padding),
        min(math.ceil(width), math.ceil(gt_right) + roi_padding),
        min(math.ceil(height), math.ceil(gt_bottom) + roi_padding),
    )
    actual = bounding_box_from_mask(_mask_in_roi(rendered_mask, roi))
    actual_left: int | None
    actual_top: int | None
    actual_right: int | None
    actual_bottom: int | None
    if actual is not None:
        actual_left, actual_top, actual_right, actual_bottom = actual
        mask_clipped = (
            actual_left > gt_left
            or actual_top > gt_top
            or actual_right < gt_right
            or actual_bottom < gt_bottom
        )
    else:
        actual_left = actual_top = actual_right = actual_bottom = None
        mask_clipped = True
    clipping = (
        gt_left < 0
        or gt_top < 0
        or gt_right > width
        or gt_bottom > height
        or mask_clipped
    )
    if actual is None:
        return PixelComparisonResult(
            gt_left,
            gt_top,
            gt_right,
            gt_bottom,
            None,
            None,
            None,
            None,
            clipping,
            None,
            0.0,
            False,
            mask_clipped,
            *roi,
        )
    actual_left, actual_top, actual_right, actual_bottom = actual
    actual_center = ((actual_left + actual_right) / 2, (actual_top + actual_bottom) / 2)
    gt_center = ((gt_left + gt_right) / 2, (gt_top + gt_bottom) / 2)
    center_error = math.hypot(
        actual_center[0] - gt_center[0], actual_center[1] - gt_center[1]
    )
    intersection = max(
        0.0, min(gt_right, actual_right) - max(gt_left, actual_left)
    ) * max(0.0, min(gt_bottom, actual_bottom) - max(gt_top, actual_top))
    gt_area = max(0.0, gt_right - gt_left) * max(0.0, gt_bottom - gt_top)
    actual_area = (actual_right - actual_left) * (actual_bottom - actual_top)
    union = gt_area + actual_area - intersection
    iou = intersection / union if union else 0.0
    within_tolerance = all(
        abs(actual_value - expected_value) <= tolerance
        for actual_value, expected_value in zip(
            (actual_left, actual_top, actual_right, actual_bottom),
            (gt_left, gt_top, gt_right, gt_bottom),
            strict=True,
        )
    )
    return PixelComparisonResult(
        gt_left,
        gt_top,
        gt_right,
        gt_bottom,
        actual_left,
        actual_top,
        actual_right,
        actual_bottom,
        clipping,
        center_error,
        iou,
        within_tolerance,
        mask_clipped,
        *roi,
    )


# Input: `mask` als rechteckige Matrix mit truthy Vordergrundpixeln.
# Output: Halb-offene Pixel-Bounding-Box oder `None` bei leerer Maske.
# Die Funktion nutzt dieselbe obere-linke Bildkonvention wie `ImagePoint`.
def bounding_box_from_mask(
    mask: Sequence[Sequence[bool | int]],
) -> tuple[int, int, int, int] | None:
    if not mask or not mask[0]:
        return None
    width = len(mask[0])
    if any(len(row) != width for row in mask):
        raise ValueError("Die Pixelmaske muss rechteckig sein.")
    foreground = [
        (x, y)
        for y, row in enumerate(mask)
        for x, value in enumerate(row)
        if bool(value)
    ]
    if not foreground:
        return None
    xs = [point[0] for point in foreground]
    ys = [point[1] for point in foreground]
    return min(xs), min(ys), max(xs) + 1, max(ys) + 1


# Input: Helligkeitsbild und Schwellwert.
# Output: Binäre Vordergrundmaske als Zeilen von `bool`.
# Dunklere Pixel werden als injizierter Text interpretiert; der Vertrag ist für
# kontrollierte, kontrastreiche Thesis-Fixtures und nicht für beliebige Fotos.
def foreground_mask(
    pixels: Sequence[Sequence[int | float]],
    threshold: float = 128,
) -> list[list[bool]]:
    if threshold < 0:
        raise ValueError("Der Pixel-Schwellwert darf nicht negativ sein.")
    return [[float(value) <= threshold for value in row] for row in pixels]


# Input: Ground-Truth-Ecken, erkannte Pixelmaske, Bildabmessungen und Toleranz.
# Output: Pixel-Bounding-Box, Clippingstatus, Mittelpunktfehler und IoU.
# Die Ground-Truth-Box wird als achsenparallele, halb-offene Box verglichen;
# leere Masken liefern `iou=0` und keinen Mittelpunktfehler.
def compare_rendered_bbox(
    corners: Sequence[Point],
    rendered_mask: Sequence[Sequence[bool | int]],
    width: float,
    height: float,
    tolerance: float = 0.0,
) -> PixelComparisonResult:
    return _compare_bbox_in_roi(
        corners,
        rendered_mask,
        width,
        height,
        tolerance,
        roi_padding=math.ceil(max(width, height)),
    )


# Input: gerendertes Rasterbild als `Path` und optionaler DICOM-Frame.
# Output: Helligkeitsmatrix mit Werten im Bereich 0 bis 255.
# JPG/PNG und gerenderte PDF-Seiten werden über Pillow gelesen; DICOM wird über
# pydicom gelesen. Ein PDF selbst muss vorab in eine Seite als Rasterbild gerendert
# sein, da dafür keine neue PDF-Rasterisierungsdependency eingeführt wird.
def load_rendered_pixels(
    image_path: Path,
    frame_index: int = 0,
) -> list[list[int]]:
    suffix = image_path.suffix.lower()
    if suffix == ".dcm":
        import numpy as np
        import pydicom

        dataset = pydicom.dcmread(image_path)
        values = np.asarray(dataset.pixel_array)
        if values.ndim == 4:
            values = values[frame_index]
        bits_stored = int(getattr(dataset, "BitsStored", 8))
        pixel_representation = int(getattr(dataset, "PixelRepresentation", 0))
        if pixel_representation == 0:
            minimum = 0.0
            maximum = float(2**bits_stored - 1)
        else:
            minimum = float(-(2 ** (bits_stored - 1)))
            maximum = float(2 ** (bits_stored - 1) - 1)
        scale = 255.0 / (maximum - minimum) if maximum > minimum else 1.0
        if values.ndim == 3 and values.shape[-1] in {3, 4}:
            values = np.asarray(values[..., :3].mean(axis=-1))
        return [
            [round((float(value) - minimum) * scale) for value in row] for row in values
        ]
    if suffix == ".pdf":
        raise ValueError(
            "PDF muss als gerendertes Seitenbild (PNG/JPG) übergeben werden."
        )
    from PIL import Image

    with Image.open(image_path) as image:
        grayscale = image.convert("L")
        return [
            [cast(int, grayscale.getpixel((x, y))) for x in range(grayscale.width)]
            for y in range(grayscale.height)
        ]


# Input: Ground-Truth-Payload, Annotation-Index und optionale PDF-Parameter.
# Output: Vier Bildpunkte fuer DICOM/JPG oder in Pixel transformierte PDF-Punkte.
# Die Funktion vereinheitlicht das kanonische RunRecord-Format, den PDF-Make-
# Sidecar und das aeltere PDF-Sidecar fuer denselben Pixelvergleich.
def _annotation_corners(
    payload: Mapping[str, Any],
    annotation_index: int,
    pdf_page_index: int | None = None,
    pdf_dpi: int | None = None,
) -> Sequence[Point]:
    if annotation_index < 0:
        raise ValueError("Der Annotation-Index darf nicht negativ sein.")
    if pdf_page_index is None:
        annotations = payload.get("box_annotations", [])
        if not isinstance(annotations, list):
            raise ValueError("box_annotations muss eine Liste sein.")
        try:
            corners = annotations[annotation_index]["corners"]
        except (IndexError, KeyError, TypeError) as error:
            raise ValueError(
                "Der Annotation-Index liegt außerhalb der Ground Truth."
            ) from error
        return cast(Sequence[Point], corners)

    pdf_entries: list[Mapping[str, Any]] = []
    for key in ("image_annotations", "text_annotations", "annotations"):
        entries = payload.get(key, [])
        if not isinstance(entries, list):
            raise ValueError(f"{key} muss eine Liste sein.")
        pdf_entries.extend(entry for entry in entries if isinstance(entry, Mapping))
    page_entries = [
        entry for entry in pdf_entries if _pdf_entry_page_index(entry) == pdf_page_index
    ]
    try:
        entry = page_entries[annotation_index]
        corners = entry["pdf_corners"]
    except (IndexError, KeyError) as error:
        raise ValueError(
            "Der PDF-Annotation-Index liegt auf dieser Seite außerhalb "
            "der Ground Truth."
        ) from error
    if pdf_dpi is None or pdf_dpi <= 0:
        raise ValueError(
            "Für PDF-Ground-Truth muss eine positive DPI angegeben werden."
        )
    page_size = _pdf_page_size(payload, pdf_page_index)
    return pdf_corners_to_pixel(cast(Sequence[Point], corners), *page_size, pdf_dpi)


# Input: Ein Eintrag aus einem PDF-Ground-Truth-Sidecar.
# Output: Zugehoeriger nullbasierter Seitenindex oder `None`.
# Die Funktion unterstuetzt sowohl direkte `page_index`-Felder als auch das
# verschachtelte Placement des `make_pdf`-Sidecars.
def _pdf_entry_page_index(entry: Mapping[str, Any]) -> int | None:
    page_index = entry.get("page_index")
    if page_index is None and isinstance(entry.get("placement"), Mapping):
        page_index = entry["placement"].get("page_index")
    return int(page_index) if isinstance(page_index, int) else None


# Input: PDF-Sidecar und nullbasierter Seitenindex.
# Output: Seitenbreite und -hoehe in PDF-Punkten.
# Die Funktion liest die im Sidecar gespeicherten Template-Metadaten und
# verhindert eine stillschweigende falsche Koordinatentransformation.
def _pdf_page_size(payload: Mapping[str, Any], page_index: int) -> tuple[float, float]:
    template = payload.get("template")
    if not isinstance(template, Mapping):
        raise ValueError("PDF-Ground-Truth enthält keine Template-Metadaten.")
    page_sizes = template.get("page_sizes")
    if (
        not isinstance(page_sizes, list)
        or page_index < 0
        or page_index >= len(page_sizes)
    ):
        raise ValueError("PDF-Seitenindex liegt außerhalb der Template-Seitengrößen.")
    page_size = page_sizes[page_index]
    if (
        not isinstance(page_size, (list, tuple))
        or len(page_size) != 2
        or not all(isinstance(value, (int, float)) for value in page_size)
    ):
        raise ValueError("PDF-Seitengröße muss aus Breite und Höhe bestehen.")
    return float(page_size[0]), float(page_size[1])


# Input: Rasterbildpfad, Ground-Truth-JSON, Annotation-Index und Vergleichsoptionen.
# Output: Serialisierbares `PixelComparisonResult` für eine sichtbare Box.
# Der Index trennt mehrere Annotationen. Eine Baseline wird bevorzugt als
# Differenzquelle verwendet; ohne Baseline bleibt der Schwellwert-Fallback für
# kontrollierte Fixtures verfügbar.
def compare_rendered_image(
    image_path: Path,
    ground_truth_path: Path,
    annotation_index: int,
    width: float,
    height: float,
    threshold: float = 128,
    tolerance: float = 0.0,
    baseline_path: Path | None = None,
    roi_padding: int = 0,
    difference_threshold: float = 0.0,
    pdf_page_index: int | None = None,
    pdf_dpi: int | None = None,
) -> PixelComparisonResult:
    payload = json.loads(ground_truth_path.read_text(encoding="utf-8-sig"))
    corners = _annotation_corners(
        payload,
        annotation_index,
        pdf_page_index=pdf_page_index,
        pdf_dpi=pdf_dpi,
    )
    pixels = load_rendered_pixels(image_path)
    if baseline_path is None:
        mask = foreground_mask(pixels, threshold)
    else:
        baseline = load_rendered_pixels(baseline_path)
        if len(pixels) != len(baseline) or any(
            len(image_row) != len(base_row)
            for image_row, base_row in zip(pixels, baseline, strict=False)
        ):
            raise ValueError("Gerendertes Bild und Baseline müssen gleich groß sein.")
        if difference_threshold < 0:
            raise ValueError("Der Differenz-Schwellwert darf nicht negativ sein.")
        mask = [
            [
                abs(value - base_value) > difference_threshold
                for value, base_value in zip(image_row, base_row, strict=True)
            ]
            for image_row, base_row in zip(pixels, baseline, strict=True)
        ]
    return _compare_bbox_in_roi(corners, mask, width, height, tolerance, roi_padding)


# Input: PDF-Punkt in PDF points, Seitengröße in Punkten und DPI.
# Output: Pixelpunkt mit oberem-linkem Ursprung.
# Die Funktion bildet die PDF-y-Achse (unten nach oben) reproduzierbar in die
# Raster-y-Achse (oben nach unten) ab.
def pdf_point_to_pixel(
    point: Point,
    page_width_pt: float,
    page_height_pt: float,
    dpi: int,
) -> dict[str, int]:
    if page_width_pt <= 0 or page_height_pt <= 0 or dpi <= 0:
        raise ValueError("Seitengröße und DPI müssen positiv sein.")
    x, y = _point_coordinates(point)
    scale = dpi / 72.0
    return {"x": round(x * scale), "y": round((page_height_pt - y) * scale)}


# Input: vier PDF-Punkte, Seitengröße in Punkten und DPI.
# Output: Vier transformierte Pixelpunkte in derselben Reihenfolge.
# Die Funktion ist der explizite Ground-Truth-Adapter für PDF-Seitenbilder.
def pdf_corners_to_pixel(
    corners: Sequence[Point],
    page_width_pt: float,
    page_height_pt: float,
    dpi: int,
) -> list[dict[str, int]]:
    return [
        pdf_point_to_pixel(point, page_width_pt, page_height_pt, dpi)
        for point in corners
    ]


# Input: PDF-Pfad, nullbasierter Seitenindex, DPI, PNG-Ziel und optionaler Renderer.
# Output: Reproduzierbare `PdfRenderResult`-Metadaten; das PNG wird geschrieben.
# Die Funktion ruft ausschließlich das vorhandene externe `pdftoppm` auf und
# liefert einen klaren Fehler, wenn der Renderer nicht gefunden werden kann.
def render_pdf_page(
    pdf_path: Path,
    page_index: int,
    dpi: int,
    output_png: Path,
    renderer: str | None = None,
) -> PdfRenderResult:
    if page_index < 0 or dpi <= 0:
        raise ValueError(
            "Seitenindex darf nicht negativ sein und DPI muss positiv sein."
        )
    renderer_path = renderer or shutil.which("pdftoppm")
    if renderer_path is None:
        raise RuntimeError(
            "pdftoppm wurde nicht gefunden. Installieren Sie Poppler oder "
            "verwenden Sie --renderer mit einem ausführbaren pdftoppm-Pfad."
        )
    output_png.parent.mkdir(parents=True, exist_ok=True)
    prefix = output_png.with_suffix("")
    command = [
        renderer_path,
        "-f",
        str(page_index + 1),
        "-l",
        str(page_index + 1),
        "-r",
        str(dpi),
        "-png",
        "-singlefile",
        str(pdf_path),
        str(prefix),
    ]
    version_result = subprocess.run(
        [renderer_path, "-v"], check=False, capture_output=True, text=True
    )
    version_stdout = getattr(version_result, "stdout", "")
    version_stderr = getattr(version_result, "stderr", "")
    if not isinstance(version_stdout, str):
        version_stdout = ""
    if not isinstance(version_stderr, str):
        version_stderr = ""
    version_output = (version_stdout + "\n" + version_stderr).strip()
    renderer_version = version_output.splitlines()[0] if version_output else "unknown"
    subprocess.run(command, check=True, capture_output=True, text=True)
    generated = prefix.with_suffix(".png")
    if generated != output_png and generated.exists():
        generated.replace(output_png)
    if not output_png.exists():
        raise RuntimeError(f"pdftoppm hat kein PNG unter {output_png} erzeugt.")
    return PdfRenderResult(
        renderer=renderer_path,
        page_index=page_index,
        dpi=dpi,
        output_png=str(output_png),
        renderer_version=renderer_version,
        render_command=command,
    )


# Input: Heatmap-Ergebnis und PNG-Zielpfad.
# Output: Keine Rückgabe; die Funktion schreibt eine einfache farbcodierte PNG-Heatmap.
# Die Darstellung verwendet Pillow ohne zusätzliche Plotting-Dependency und
# bewahrt die Zeilen-/Spaltenstruktur des 2D-Histogramms.
def write_heatmap_png(result: Mapping[str, Any], output_path: Path) -> None:
    heatmap = result.get("heatmap")
    if not isinstance(heatmap, list) or not heatmap:
        raise ValueError("Das Heatmap-Ergebnis enthält keine Daten.")
    from PIL import Image

    rows = len(heatmap)
    columns = len(heatmap[0])
    maximum = max(max(int(value) for value in row) for row in heatmap) or 1
    image = Image.new("RGB", (columns, rows), color=(255, 255, 255))
    for y, row in enumerate(heatmap):
        for x, value in enumerate(row):
            intensity = round(255 * int(value) / maximum)
            image.putpixel((x, y), (255, 255 - intensity, 255 - intensity))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, format="PNG")


# Input: Wert und gültiger Bereich mit unterer/oberer Grenze.
# Output: Wert linear auf den Bereich [0, 1] abgebildet.
# Die Funktion wird nur für bereits gültige Mittelpunkte verwendet.
def _normalize_to_range(value: float, value_range: tuple[float, float]) -> float:
    lower, upper = value_range
    if upper <= lower:
        return 0.5
    return (value - lower) / (upper - lower)


# Input: Koordinatenserien, Bildgröße, Binning und Placement-Modus.
# Output: Normalisierte Boxen/Mittelpunkte, Häufigkeiten, Heatmap und Chi-Quadrat-Test.
# Für `free` wird Gleichverteilung über 2D-Bins, für `corners` Gleichverteilung
# über vier Eckbereiche als Nullhypothese verwendet.
def analyse_distribution(
    samples: Sequence[Sequence[Point]],
    width: float,
    height: float,
    placement_mode: str,
    bins: int = 10,
) -> dict[str, Any]:
    if width <= 0 or height <= 0 or bins <= 0:
        raise ValueError("Bildgröße und Binning müssen positiv sein.")
    if placement_mode not in {"corners", "free"}:
        raise ValueError("placement_mode muss 'corners' oder 'free' sein.")
    normalized_boxes = [
        normalize_bounding_box(sample, width, height) for sample in samples
    ]
    centers = [{"x": box["center_x"], "y": box["center_y"]} for box in normalized_boxes]
    sample_details: list[dict[str, Any]] = []
    adjusted_centers: list[dict[str, float] | None] = []
    valid_indices: list[int] = []
    adjusted: dict[str, float] | None
    for index, (box, normalized_center) in enumerate(
        zip(normalized_boxes, centers, strict=True)
    ):
        half_width = (box["right"] - box["left"]) / 2
        half_height = (box["bottom"] - box["top"]) / 2
        x_range = (half_width, 1.0 - half_width)
        y_range = (half_height, 1.0 - half_height)
        valid = (
            x_range[0] <= normalized_center["x"] <= x_range[1]
            and y_range[0] <= normalized_center["y"] <= y_range[1]
        )
        adjusted = None
        if valid:
            adjusted = {
                "x": _normalize_to_range(normalized_center["x"], x_range),
                "y": _normalize_to_range(normalized_center["y"], y_range),
            }
            valid_indices.append(index)
        adjusted_centers.append(adjusted)
        sample_details.append(
            {
                "center_range_x": list(x_range),
                "center_range_y": list(y_range),
                "valid_center": valid,
            }
        )
    heatmap = [[0 for _ in range(bins)] for _ in range(bins)]
    for index in valid_indices:
        center = adjusted_centers[index]
        assert center is not None
        x_bin = min(bins - 1, max(0, int(center["x"] * bins)))
        y_bin = min(bins - 1, max(0, int(center["y"] * bins)))
        heatmap[y_bin][x_bin] += 1
    corner_counts = {
        name: 0 for name in ("top_left", "top_right", "bottom_left", "bottom_right")
    }
    outside_corner_count = 0
    for sample_center in centers:
        horizontal = (
            "left"
            if sample_center["x"] < 0.25
            else "right"
            if sample_center["x"] >= 0.75
            else None
        )
        vertical = (
            "top"
            if sample_center["y"] < 0.25
            else "bottom"
            if sample_center["y"] >= 0.75
            else None
        )
        if horizontal is None or vertical is None:
            outside_corner_count += 1
        else:
            corner_counts[f"{vertical}_{horizontal}"] += 1
    observed = (
        list(corner_counts.values())
        if placement_mode == "corners"
        else [count for row in heatmap for count in row]
    )
    expected_total = (
        sum(corner_counts.values())
        if placement_mode == "corners"
        else len(valid_indices)
    )
    expected = [expected_total / len(observed) for _ in observed] if observed else []
    chi_square = sum(
        (actual - target) ** 2 / target
        for actual, target in zip(observed, expected, strict=True)
        if target > 0
    )
    degrees_of_freedom = max(0, len(observed) - 1)
    return {
        "placement_mode": placement_mode,
        "sample_count": len(samples),
        "bins": bins,
        "normalized_centers": centers,
        "normalized_bounding_boxes": normalized_boxes,
        "sample_details": sample_details,
        "adjusted_centers": adjusted_centers,
        "corner_counts": corner_counts,
        "outside_corner_count": outside_corner_count,
        "outside_valid_count": len(samples) - len(valid_indices),
        "heatmap": heatmap,
        "expected_counts": expected,
        "chi_square": chi_square,
        "degrees_of_freedom": degrees_of_freedom,
        "chi_square_p_value": _chi_square_survival(chi_square, degrees_of_freedom),
    }


# Input: Chi-Quadrat-Wert und Freiheitsgrade.
# Output: Näherungsweiser p-Wert der oberen Chi-Quadrat-Verteilung.
# Die Implementierung nutzt nur die Standardbibliothek und ist für die
# Verteilungsdiagnostik, nicht für eine inferenzstatistische Hauptanalyse gedacht.
def _chi_square_survival(value: float, degrees_of_freedom: int) -> float | None:
    if degrees_of_freedom <= 0:
        return None
    shape = degrees_of_freedom / 2.0
    argument = value / 2.0
    if argument == 0:
        return 1.0
    tiny = 1e-300
    if argument < shape + 1:
        term = 1.0 / shape
        total = term
        for _ in range(200):
            term *= argument / (shape + _ + 1)
            total += term
            if abs(term) < abs(total) * 1e-14:
                break
        lower = total * math.exp(
            -argument + shape * math.log(argument) - math.lgamma(shape)
        )
        return max(0.0, min(1.0, 1.0 - lower))
    b = argument + 1.0 - shape
    c = 1.0 / tiny
    d = 1.0 / max(b, tiny)
    fraction = d
    for _ in range(200):
        index = _ + 1
        an = -index * (index - shape)
        b += 2.0
        d = 1.0 / max(an * d + b, tiny)
        c = max(b + an / c, tiny)
        delta = c * d
        fraction *= delta
        if abs(delta - 1.0) < 1e-14:
            break
    upper = fraction * math.exp(
        -argument + shape * math.log(argument) - math.lgamma(shape)
    )
    return max(0.0, min(1.0, upper))


# Input: `point` als ImagePoint-kompatibles Mapping oder Zweier-Tupel.
# Output: `x`, `y`-Koordinaten als Tupel.
# Die Funktion unterstützt Ground-Truth-Dictionaries und einfache Fixture-Punkte.
def _point_coordinates(point: Point) -> tuple[float, float]:
    if isinstance(point, Mapping):
        x_value = point.get("x")
        y_value = point.get("y")
        if x_value is None or y_value is None:
            raise ValueError("Ein Punkt muss die Felder 'x' und 'y' enthalten.")
        return float(x_value), float(y_value)
    if len(point) != 2:
        raise ValueError("Ein Punkt muss genau zwei Koordinaten enthalten.")
    return float(point[0]), float(point[1])


# Input: `corners` mit vier Punkten im Bildkoordinatensystem.
# Output: Achsenparallele Bounding Box als `(left, top, right, bottom)`.
# Die Box wird aus allen vier Quad-Ecken abgeleitet und unterstützt auch rotierte
# Ground-Truth-Quads konservativ.
def bounding_box_from_corners(
    corners: Sequence[Point],
) -> tuple[float, float, float, float]:
    if len(corners) != 4:
        raise ValueError("Eine Ground-Truth-Box muss genau vier Ecken enthalten.")
    coordinates = [_point_coordinates(point) for point in corners]
    values_x = [coordinate[0] for coordinate in coordinates]
    values_y = [coordinate[1] for coordinate in coordinates]
    return min(values_x), min(values_y), max(values_x), max(values_y)


# Input: Box-Ecken und positive Bildbreite/-höhe.
# Output: Bounding-Box-Werte mit auf Bildgröße normiertem Mittelpunkt.
# Auch ungültige Boxen werden normiert, damit Grenzverletzungen sichtbar bleiben.
def normalize_bounding_box(
    corners: Sequence[Point],
    width: float,
    height: float,
) -> dict[str, float]:
    if width <= 0 or height <= 0:
        raise ValueError("Bildbreite und Bildhöhe müssen positiv sein.")
    left, top, right, bottom = bounding_box_from_corners(corners)
    return {
        "left": left / width,
        "top": top / height,
        "right": right / width,
        "bottom": bottom / height,
        "center_x": (left + right) / 2 / width,
        "center_y": (top + bottom) / 2 / height,
    }


# Input: Box-Ecken, Bildabmessungen und optionale numerische Toleranz.
# Output: Vollständiges `BoundingBoxResult` mit Grenz- und Clipping-Befund.
# Die Toleranz bildet kleine Render-/Rundungsabweichungen ab; standardmäßig muss
# die gesamte achsenparallele Box innerhalb des Bildes liegen.
def validate_bounding_box(
    corners: Sequence[Point],
    width: float,
    height: float,
    tolerance: float = 0.0,
) -> BoundingBoxResult:
    if width <= 0 or height <= 0:
        raise ValueError("Bildbreite und Bildhöhe müssen positiv sein.")
    if tolerance < 0:
        raise ValueError("Die Toleranz darf nicht negativ sein.")
    left, top, right, bottom = bounding_box_from_corners(corners)
    values = (left, top, right, bottom)
    if not all(math.isfinite(value) for value in values):
        raise ValueError("Bounding-Box-Koordinaten müssen endlich sein.")
    issues: list[str] = []
    if left < -tolerance:
        issues.append("left_out_of_bounds")
    if top < -tolerance:
        issues.append("top_out_of_bounds")
    if right > width + tolerance:
        issues.append("right_out_of_bounds")
    if bottom > height + tolerance:
        issues.append("bottom_out_of_bounds")
    valid = not issues
    return BoundingBoxResult(
        left=left,
        top=top,
        right=right,
        bottom=bottom,
        center_x=(left + right) / 2,
        center_y=(top + bottom) / 2,
        within_bounds=valid,
        text_not_clipped=valid,
        issues=";".join(issues),
    )


# Input: Ground-Truth-JSON und Bildabmessungen.
# Output: Eine CSV-kompatible Zeile pro `box_annotations`-Eintrag.
# Die Funktion bewahrt `run_id`, `document_type`, `region` und `frame_index`.
def analyse_ground_truth(
    ground_truth_path: Path,
    width: float,
    height: float,
    tolerance: float = 0.0,
) -> list[dict[str, Any]]:
    payload = json.loads(ground_truth_path.read_text(encoding="utf-8-sig"))
    rows: list[dict[str, Any]] = []
    for annotation in payload.get("box_annotations", []):
        corners = annotation["corners"]
        result = validate_bounding_box(corners, width, height, tolerance)
        normalized = normalize_bounding_box(corners, width, height)
        rows.append(
            {
                "run_id": payload.get("run_id", ""),
                "document_type": payload.get("document_type", ""),
                "label": annotation.get("label", ""),
                "region": annotation.get("region", ""),
                "frame_index": annotation.get("frame_index", ""),
                "width": width,
                "height": height,
                **asdict(result),
                **{f"normalized_{key}": value for key, value in normalized.items()},
            }
        )
    return rows


# Input: Auswertungszeilen und Zielpfad.
# Output: Keine Rückgabe; die Funktion schreibt eine deterministische CSV-Datei.
# Die feste Spaltenreihenfolge macht Ergebnisse zwischen Läufen vergleichbar.
def write_results_csv(rows: Sequence[dict[str, Any]], output_path: Path) -> None:
    fieldnames = [
        "run_id",
        "document_type",
        "label",
        "region",
        "frame_index",
        "width",
        "height",
        "left",
        "top",
        "right",
        "bottom",
        "center_x",
        "center_y",
        "within_bounds",
        "text_not_clipped",
        "issues",
        "normalized_left",
        "normalized_top",
        "normalized_right",
        "normalized_bottom",
        "normalized_center_x",
        "normalized_center_y",
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


# Input: CLI-Argumente für Ground Truth, Bildgröße, Toleranz und CSV-Ziel.
# Output: Exit-Code 0 nach erfolgreicher Analyse.
# Das Kommando erzeugt nur die ausdrücklich angegebene Ergebnis-CSV.
# Input: JSON-Payload als Ground-Truth-Record, Record-Liste oder Sample-Liste.
# Output: Liste von `corners`-Samples für `analyse_distribution`.
# Die Funktion vereinheitlicht die vom CLI unterstützten Eingabeformen.
def _distribution_samples_from_payload(payload: Any) -> list[Sequence[Point]]:
    if isinstance(payload, Mapping):
        return [
            annotation["corners"] for annotation in payload.get("box_annotations", [])
        ]
    if not isinstance(payload, list):
        raise ValueError("Die Verteilungseingabe muss JSON-Objekt oder Liste sein.")
    if payload and isinstance(payload[0], Mapping) and "x" in payload[0]:
        return [payload]
    samples: list[Sequence[Point]] = []
    for entry in payload:
        if isinstance(entry, Mapping) and "box_annotations" in entry:
            samples.extend(_distribution_samples_from_payload(entry))
        elif isinstance(entry, Mapping) and "corners" in entry:
            samples.append(entry["corners"])
        elif isinstance(entry, list):
            samples.append(entry)
        else:
            raise ValueError("Unbekanntes Format in der Verteilungseingabe.")
    return samples


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ground-truth", type=Path)
    parser.add_argument("--width", type=float)
    parser.add_argument("--height", type=float)
    parser.add_argument("--tolerance", type=float, default=0.0)
    parser.add_argument("--output-csv", type=Path)
    parser.add_argument("--rendered-image", type=Path)
    parser.add_argument("--baseline-image", type=Path)
    parser.add_argument("--annotation-index", type=int, default=0)
    parser.add_argument("--threshold", type=float, default=128)
    parser.add_argument(
        "--allow-threshold-fallback",
        action="store_true",
        help=(
            "Erlaubt den globalen Helligkeitsschwellwert ohne Baseline "
            "(nur kontrollierte Fixtures)."
        ),
    )
    parser.add_argument("--difference-threshold", type=float, default=0)
    parser.add_argument("--roi-padding", type=int, default=0)
    parser.add_argument("--pixel-output-json", type=Path)
    parser.add_argument("--distribution-input", type=Path)
    parser.add_argument("--placement-mode", choices=("corners", "free"))
    parser.add_argument("--bins", type=int, default=10)
    parser.add_argument("--distribution-output-json", type=Path)
    parser.add_argument("--heatmap-png", type=Path)
    parser.add_argument("--pdf", type=Path)
    parser.add_argument(
        "--pdf-ground-truth",
        action="store_true",
        help=(
            "Interpretiert --ground-truth als PDF-Sidecar und transformiert "
            "pdf_corners."
        ),
    )
    parser.add_argument("--pdf-page-index", type=int, default=0)
    parser.add_argument("--pdf-dpi", type=int, default=150)
    parser.add_argument("--pdf-output-png", type=Path)
    parser.add_argument("--pdf-metadata-json", type=Path)
    parser.add_argument("--renderer")
    args = parser.parse_args()
    if any((args.output_csv, args.rendered_image, args.distribution_input)) and (
        args.width is None or args.height is None
    ):
        parser.error("Diese Auswertung benötigt --width und --height.")
    if args.ground_truth and args.output_csv:
        rows = analyse_ground_truth(
            args.ground_truth, args.width, args.height, args.tolerance
        )
        write_results_csv(rows, args.output_csv)
        print(f"{len(rows)} Box-Annotationen nach {args.output_csv} geschrieben.")
    if args.rendered_image:
        if not args.ground_truth or not args.pixel_output_json:
            parser.error(
                "Pixelvergleich benötigt --ground-truth und --pixel-output-json."
            )
        if args.baseline_image is None and not args.allow_threshold_fallback:
            parser.error(
                "Für die Evaluation ist --baseline-image erforderlich; "
                "für kontrollierte Fixtures zusätzlich "
                "--allow-threshold-fallback setzen."
            )
        comparison = compare_rendered_image(
            args.rendered_image,
            args.ground_truth,
            args.annotation_index,
            args.width,
            args.height,
            args.threshold,
            args.tolerance,
            args.baseline_image,
            args.roi_padding,
            args.difference_threshold,
            args.pdf_page_index if args.pdf_ground_truth else None,
            args.pdf_dpi if args.pdf_ground_truth else None,
        )
        args.pixel_output_json.parent.mkdir(parents=True, exist_ok=True)
        args.pixel_output_json.write_text(
            json.dumps(asdict(comparison), indent=2), encoding="utf-8"
        )
        print(f"Pixelvergleich nach {args.pixel_output_json} geschrieben.")
    if args.distribution_input:
        if (
            not args.placement_mode
            or not args.distribution_output_json
            or not args.heatmap_png
        ):
            parser.error(
                "Verteilung benötigt --placement-mode, --distribution-output-json "
                "und --heatmap-png."
            )
        payload = json.loads(args.distribution_input.read_text(encoding="utf-8-sig"))
        samples = _distribution_samples_from_payload(payload)
        result = analyse_distribution(
            samples, args.width, args.height, args.placement_mode, args.bins
        )
        args.distribution_output_json.parent.mkdir(parents=True, exist_ok=True)
        args.distribution_output_json.write_text(
            json.dumps(result, indent=2), encoding="utf-8"
        )
        write_heatmap_png(result, args.heatmap_png)
        print(f"Verteilung nach {args.distribution_output_json} geschrieben.")
    if args.pdf:
        if not args.pdf_output_png or not args.pdf_metadata_json:
            parser.error("PDF benötigt --pdf-output-png und --pdf-metadata-json.")
        pdf_result = render_pdf_page(
            args.pdf,
            args.pdf_page_index,
            args.pdf_dpi,
            args.pdf_output_png,
            args.renderer,
        )
        args.pdf_metadata_json.parent.mkdir(parents=True, exist_ok=True)
        args.pdf_metadata_json.write_text(
            json.dumps(asdict(pdf_result), indent=2), encoding="utf-8"
        )
        print(f"PDF-Seite nach {args.pdf_output_png} gerendert.")
    if not any(
        (args.output_csv, args.rendered_image, args.distribution_input, args.pdf)
    ):
        parser.error("Mindestens eine Auswertung muss angegeben werden.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
