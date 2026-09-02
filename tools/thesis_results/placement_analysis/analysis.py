"""Deskriptive, auditierbare Auswertung von Ground-Truth-Platzierungen."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import statistics
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from pydicom.errors import InvalidDicomError
from tools.thesis_results.coordinate_validation.coordinate_validation import (
    bounding_box_from_corners,
    normalize_bounding_box,
    validate_bounding_box,
)

CORNER_REGIONS = ("top_left", "top_right", "bottom_left", "bottom_right", "none")
FINGERPRINT_FIELDS = (
    "seed",
    "placement_mode",
    "input_fingerprint",
    "rotation",
    "document_type",
    "width",
    "height",
    "font",
    "font_size",
    "box_geometry",
)
SUMMARY_FIELDS = (
    "center_x",
    "center_y",
    "edge_distance",
    "normalized_width",
    "normalized_height",
    "normalized_area",
    "aspect_ratio",
)
BOX_FIELDS = (
    "run_id",
    "run_fingerprint",
    "seed",
    "placement_mode",
    "document_type",
    "rotation",
    "font",
    "font_size",
    "width",
    "height",
    "dimension_source",
    "label",
    "annotation_index",
    "left",
    "top",
    "right",
    "bottom",
    "normalized_left",
    "normalized_top",
    "normalized_right",
    "normalized_bottom",
    "center_x",
    "center_y",
    "normalized_width",
    "normalized_height",
    "normalized_area",
    "aspect_ratio",
    "edge_distance",
    "declared_region",
    "center_region",
    "within_bounds",
    "text_not_clipped",
    "clipped",
    "geometric_outside",
    "pixel_comparison_error",
    "issues",
)


# Input: Ground-Truth-Pfad, Payload und optionaler Dimensionsfallback.
# Output: Dimensionen sowie deren nachvollziehbare Quelle und Status.
# Referenzen werden in der Reihenfolge Preview, Output, Source und Fallback geprüft.
def image_dimensions_with_source(
    ground_truth_path: Path,
    payload: Mapping[str, Any],
    fallback_width: float | None = None,
    fallback_height: float | None = None,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    references = (
        ("preview", ("preview_file", "preview.png")),
        ("output_file", ("output_file",)),
        ("source_file", ("source_file",)),
    )
    failures: list[str] = []
    for source, names in references:
        for name in names:
            candidates = (
                [ground_truth_path.parent / "preview.png"]
                if name == "preview.png"
                else _reference_paths(ground_truth_path, payload.get(name), repo_root)
            )
            for candidate in candidates:
                dimensions = _read_dimensions(candidate)
                if dimensions is not None:
                    return {
                        "width": dimensions[0],
                        "height": dimensions[1],
                        "source": source,
                    }
                if candidate.is_file():
                    kind = (
                        "invalid_dicom"
                        if candidate.suffix.casefold() in {".dcm", ".dicom"}
                        else "unreadable_image"
                    )
                    failures.append(f"{source}:{kind}")
    if fallback_width is not None or fallback_height is not None:
        if fallback_width is None or fallback_height is None:
            raise ValueError(
                "Fallback-Bildabmessungen müssen gemeinsam angegeben werden."
            )
        if fallback_width <= 0 or fallback_height <= 0:
            raise ValueError("Fallback-Bildabmessungen müssen positiv sein.")
        return {
            "width": fallback_width,
            "height": fallback_height,
            "source": "fallback",
        }
    return {
        "width": None,
        "height": None,
        "source": None,
        "missing_information": ["dimensions", *failures],
    }


# Input: Ground-Truth-Pfad und optionale Pfadreferenz.
# Output: Kandidaten in relativer und absoluter Auflösung.
# Die Funktion liest nur Pfade und verändert keine Daten.
def _reference_paths(
    ground_truth_path: Path, value: Any, repo_root: Path | None
) -> list[Path]:
    if not isinstance(value, (str, Path)) or not str(value):
        return []
    path = Path(value)
    if path.is_absolute():
        return [path]
    root = repo_root or _discover_repo_root(ground_truth_path)
    return [ground_truth_path.parent / path, root / path]


# Input: JPG/JPEG/PNG/TIFF/BMP- oder DICOM-Pfad.
# Output: `(width, height)` oder `None`, wenn das Format nicht lesbar ist.
# Pillow liest Rasterbilder; pydicom liest DICOM Rows und Columns ohne Pixeldecoding.
def _read_dimensions(path: Path) -> tuple[float, float] | None:
    if not path.is_file():
        return None
    try:
        if path.suffix.casefold() in {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}:
            from PIL import Image

            with Image.open(path) as image:
                return float(image.width), float(image.height)
        if path.suffix.casefold() in {".dcm", ".dicom"}:
            import pydicom

            dataset = pydicom.dcmread(str(path), stop_before_pixels=True)
            return float(dataset.Columns), float(dataset.Rows)
    except (
        AttributeError,
        EOFError,
        InvalidDicomError,
        OSError,
        TypeError,
        ValueError,
    ):
        return None
    return None


# Input: Ground-Truth-Payload und optionale Dimensionsparameter.
# Output: Erkannte `(width, height)` oder `None` ohne verlässliche Dimensionen.
# Diese Kompatibilitätsfunktion bewahrt die bisherige öffentliche API.
def image_dimensions(
    ground_truth_path: Path,
    payload: Mapping[str, Any],
    fallback_width: float | None = None,
    fallback_height: float | None = None,
    repo_root: Path | None = None,
) -> tuple[float, float] | None:
    result = image_dimensions_with_source(
        ground_truth_path, payload, fallback_width, fallback_height, repo_root
    )
    if result["width"] is None or result["height"] is None:
        return None
    return float(result["width"]), float(result["height"])


# Input: Ground-Truth-Pfad.
# Output: Erkannter Repository-Root oder aktuelles Arbeitsverzeichnis als Fallback.
# Die Suche nutzt `pyproject.toml` statt eines hardcodierten Benutzerpfads.
def _discover_repo_root(ground_truth_path: Path) -> Path:
    current = ground_truth_path.resolve().parent
    for candidate in (current, *current.parents):
        if (candidate / "pyproject.toml").is_file():
            return candidate
    return Path.cwd()


# Input: Payload, Annotation, Feldnamen und Standardwert.
# Output: Der erste passende Wert aus Annotation, Payload oder Metadaten.
# Damit bleiben alte und aktuelle Ground-Truth-Schemata auswertbar.
def _metadata(
    payload: Mapping[str, Any],
    annotation: Mapping[str, Any],
    names: Sequence[str],
    default: Any = "",
) -> Any:
    for source in (annotation, payload):
        for name in names:
            if name in source and source[name] is not None:
                return source[name]
    for nested_name in ("render_metadata", "run_metadata"):
        nested = payload.get(nested_name)
        if isinstance(nested, Mapping):
            for name in names:
                if name in nested and nested[name] is not None:
                    return nested[name]
    return default


# Input: Normalisierte Box-Mittelpunkte in `[0, 1]`.
# Output: Eckregion oder `none` bei fehlender Eckzuordnung.
# Die 25-Prozent-Schwelle entspricht der bestehenden Koordinatenvalidierung.
def classify_corner(center_x: float, center_y: float) -> str:
    horizontal = "left" if center_x < 0.25 else "right" if center_x >= 0.75 else ""
    vertical = "top" if center_y < 0.25 else "bottom" if center_y >= 0.75 else ""
    return f"{vertical}_{horizontal}" if horizontal and vertical else "none"


# Input: Zwei achsenparallele Boxen `(left, top, right, bottom)`.
# Output: `True` bei einer Fläche positiver Breite und Höhe.
# Kantenkontakt zählt nicht; die Metrik ist kein Masken- oder Polygon-Overlap.
def boxes_overlap(first: Sequence[float], second: Sequence[float]) -> bool:
    return min(first[2], second[2]) > max(first[0], second[0]) and min(
        first[3], second[3]
    ) > max(first[1], second[1])


# Input: Ground-Truth-Datei, Payload, Bildmaße und Annotation.
# Output: Eine CSV-kompatible Boxzeile mit deklarierter und berechneter Region.
# Pixelvergleichswerte werden nur übernommen, wenn sie im Payload vorhanden sind.
def extract_box_metrics(
    ground_truth_path: Path,
    payload: Mapping[str, Any],
    width: float,
    height: float,
    annotation: Mapping[str, Any],
    annotation_index: int,
    dimension_source: str = "provided",
    run_fingerprint: str = "",
) -> dict[str, Any]:
    corners = annotation["corners"]
    box = bounding_box_from_corners(corners)
    normalized = normalize_bounding_box(corners, width, height)
    validation = validate_bounding_box(corners, width, height)
    left, top, right, bottom = box
    box_width, box_height = right - left, bottom - top
    area = max(0.0, box_width) * max(0.0, box_height)
    center_x, center_y = normalized["center_x"], normalized["center_y"]
    pixel_error = _pixel_error(payload, annotation, annotation_index)
    center_region = classify_corner(center_x, center_y)
    return {
        "run_id": _metadata(payload, annotation, ("run_id",), ground_truth_path.stem),
        "run_fingerprint": run_fingerprint,
        "seed": _metadata(payload, annotation, ("seed",)),
        "placement_mode": _metadata(
            payload, annotation, ("placement_mode",), "unknown"
        ),
        "document_type": _metadata(payload, annotation, ("document_type",), "unknown"),
        "rotation": _metadata(payload, annotation, ("rotation", "rotation_degrees")),
        "font": _metadata(
            payload, annotation, ("font", "font_family", "effective_font_family")
        ),
        "font_size": _metadata(payload, annotation, ("font_size", "font_size_pct")),
        "width": width,
        "height": height,
        "dimension_source": dimension_source,
        "label": annotation.get("label", ""),
        "annotation_index": annotation_index,
        "left": left,
        "top": top,
        "right": right,
        "bottom": bottom,
        **{f"normalized_{key}": value for key, value in normalized.items()},
        "center_x": center_x,
        "center_y": center_y,
        "normalized_width": box_width / width,
        "normalized_height": box_height / height,
        "normalized_area": area / (width * height),
        "aspect_ratio": box_width / box_height if box_height else math.inf,
        "edge_distance": min(
            normalized["left"],
            normalized["top"],
            1 - normalized["right"],
            1 - normalized["bottom"],
        ),
        "declared_region": annotation.get("region", ""),
        "center_region": center_region,
        "corner_region": center_region,
        "within_bounds": validation.within_bounds,
        "text_not_clipped": validation.text_not_clipped,
        "clipped": not validation.within_bounds,
        "geometric_outside": not validation.within_bounds,
        "pixel_comparison_error": pixel_error,
        "issues": validation.issues,
    }


# Input: Payload, Annotation und Annotationindex.
# Output: Optionaler numerischer Pixelvergleichsfehler oder `None`.
# Unbekannte Pixelvergleichsformate werden nicht als Clipping fehlklassifiziert.
def _pixel_error(
    payload: Mapping[str, Any], annotation: Mapping[str, Any], index: int
) -> float | None:
    for source in (annotation, payload):
        for key in ("pixel_comparison_error", "pixel_error", "pixel_diff_error"):
            value = source.get(key)
            if isinstance(value, (int, float)):
                return float(value)
    for key in ("pixel_comparison_errors", "pixel_comparison"):
        values = payload.get(key)
        if (
            isinstance(values, Sequence)
            and not isinstance(values, (str, bytes))
            and index < len(values)
        ):
            value = values[index]
            if isinstance(value, Mapping):
                value = value.get("error", value.get("max_difference"))
            if isinstance(value, (int, float)):
                return float(value)
    return None


# Input: Boxmetriken eines Runs.
# Output: Run-Zeile mit deskriptiven Box-, Regions-, Clipping- und Overlapwerten.
# Bounding-Box-Overlap wird ausdrücklich nicht als Masken- oder
# Polygon-Overlap bezeichnet.
def summarize_run(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise ValueError("Ein Run muss mindestens eine Box enthalten.")
    boxes = [
        (
            float(row["left"]),
            float(row["top"]),
            float(row["right"]),
            float(row["bottom"]),
        )
        for row in rows
    ]
    overlap_count = sum(
        boxes_overlap(boxes[i], boxes[j])
        for i in range(len(boxes))
        for j in range(i + 1, len(boxes))
    )
    pair_count = len(boxes) * (len(boxes) - 1) // 2
    result: dict[str, Any] = {
        key: rows[0].get(key, "")
        for key in (
            "run_id",
            "run_fingerprint",
            "seed",
            "placement_mode",
            "document_type",
            "rotation",
            "font",
            "font_size",
            "width",
            "height",
            "dimension_source",
        )
    }
    result.update(
        {
            "box_count": len(rows),
            "geometric_clipped_box_count": sum(
                bool(row["geometric_outside"]) for row in rows
            ),
            "pixel_comparison_error_count": sum(
                row["pixel_comparison_error"] is not None for row in rows
            ),
            "pixel_comparison_errors": [
                row["pixel_comparison_error"]
                for row in rows
                if row["pixel_comparison_error"] is not None
            ],
            "overlap_pair_count": overlap_count,
            "overlap_pair_total": pair_count,
            "overlap_pair_share": overlap_count / pair_count if pair_count else 0.0,
            "overlap_definition": (
                "achsenparallele Bounding-Box-Paare; kein Masken- oder Polygon-Overlap"
            ),
        }
    )
    for region_name, field_name in (
        ("declared_region", "declared_corner_share"),
        ("center_region", "center_corner_share"),
    ):
        counts = Counter(str(row[region_name]) for row in rows)
        for region in CORNER_REGIONS:
            result[f"{field_name}_{region}"] = counts[region] / len(rows)
    for region in CORNER_REGIONS:
        result[f"corner_share_{region}"] = result[f"center_corner_share_{region}"]
    return result


# Input: Numerische Werte einer Kennzahl.
# Output: n, Lage-, Streuungs- und Perzentilkennzahlen.
# Bei leerer Eingabe werden nur `n=0` und leere Werte ausgegeben.
def descriptive_statistics(values: Sequence[float]) -> dict[str, float | int | None]:
    ordered = sorted(float(value) for value in values if math.isfinite(float(value)))
    if not ordered:
        return {
            "n": 0,
            "mean": None,
            "median": None,
            "std": None,
            "iqr": None,
            "min": None,
            "max": None,
            "p05": None,
            "p95": None,
        }
    return {
        "n": len(ordered),
        "mean": statistics.fmean(ordered),
        "median": statistics.median(ordered),
        "std": statistics.stdev(ordered) if len(ordered) > 1 else 0.0,
        "iqr": _percentile(ordered, 75) - _percentile(ordered, 25),
        "min": ordered[0],
        "max": ordered[-1],
        "p05": _percentile(ordered, 5),
        "p95": _percentile(ordered, 95),
    }


# Input: Sortierte Werte und Quantil in Prozent.
# Output: Linear interpoliertes Quantil.
# Die Standardbibliothek bleibt damit ausreichend und deterministisch.
def _percentile(values: Sequence[float], percentile: float) -> float:
    if not values:
        raise ValueError("Quantil benötigt mindestens einen Wert.")
    position = (len(values) - 1) * percentile / 100
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return float(values[lower])
    weight = position - lower
    return float(values[lower] * (1 - weight) + values[upper] * weight)


# Input: Run- und Boxzeilen, Zielverzeichnis, Manifest und Binning.
# Output: Keine Rückgabe; schreibt CSV-, JSON-, Manifest- und Plotartefakte.
# Globale Vergleichsplots entstehen ausschließlich aus freigegebenen Konfigurationen.
def write_analysis_outputs(
    box_rows: Sequence[dict[str, Any]],
    run_rows: Sequence[dict[str, Any]],
    output_dir: Path,
    manifest: Mapping[str, Any],
    bins: int,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(box_rows, output_dir / "box_metrics.csv", BOX_FIELDS)
    run_fields = tuple(run_rows[0].keys()) if run_rows else ("run_id", "box_count")
    _write_csv(run_rows, output_dir / "run_summary.csv", run_fields)
    comparable_keys = _comparable_configuration_keys(run_rows)
    summary = {
        "box_count": len(box_rows),
        "run_count": len(run_rows),
        "mode_box_counts": dict(
            Counter(str(row["placement_mode"]) for row in box_rows)
        ),
        "mode_run_counts": dict(
            Counter(str(row["placement_mode"]) for row in run_rows)
        ),
        "unbalanced_groups": manifest.get("unbalanced_groups", []),
        "configuration_summaries": _configuration_summaries(run_rows),
        "descriptive_statistics": _summary_statistics(box_rows),
        "clipping": _clipping_summary(box_rows),
        "overlap": _overlap_summary(run_rows),
        "mode_comparison_suppressed": not comparable_keys,
        "comparable_configuration_count": len(comparable_keys),
        "inferential_tests": [],
        "notes": [
            "Deskriptive Auswertung; keine p-Werte oder Hypothesentests.",
            "Bounding-Box-Overlap ist nicht Masken- oder Polygon-Overlap.",
        ],
    }
    (output_dir / "descriptive_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    plot_files = _write_plots(box_rows, output_dir / "plots", bins, comparable_keys)
    manifest_data = {
        **manifest,
        "bins": bins,
        "fingerprint_definition": list(FINGERPRINT_FIELDS),
        "mode_comparison_suppressed": not comparable_keys,
        "comparable_configuration_count": len(comparable_keys),
        "comparable_configurations": [
            _configuration_dict(key) for key in sorted(comparable_keys)
        ],
        "outputs": [
            "box_metrics.csv",
            "run_summary.csv",
            "descriptive_summary.json",
            "analysis_manifest.json",
            "plots/",
        ],
        "plot_files": plot_files,
    }
    (output_dir / "analysis_manifest.json").write_text(
        json.dumps(manifest_data, indent=2), encoding="utf-8"
    )


# Input: Zeilen, Pfad und feste Spaltenreihenfolge.
# Output: Keine Rückgabe; schreibt eine UTF-8-CSV.
def _write_csv(
    rows: Sequence[Mapping[str, Any]], path: Path, fields: Sequence[str]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


# Input: Boxzeilen.
# Output: Deskriptive Kennzahlen je vollständiger Konfiguration und Modus.
# Die Kennzahlen werden auf Boxebene mit den geforderten Quartilen berechnet.
def _summary_statistics(box_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    groups: dict[tuple[str, ...], list[Mapping[str, Any]]] = defaultdict(list)
    for row in box_rows:
        groups[(*_configuration_key(row), str(row.get("placement_mode", "")))].append(
            row
        )
    return {
        "by_mode_and_configuration": [
            {
                "configuration": _configuration_dict(key[:-1]),
                "placement_mode": key[-1],
                "metrics": {
                    field: descriptive_statistics([float(row[field]) for row in rows])
                    for field in SUMMARY_FIELDS
                },
            }
            for key, rows in sorted(groups.items())
        ]
    }


# Input: Boxzeilen.
# Output: Geometrische und optionale Pixelvergleichs-Zählungen und Anteile.
# Fehlende Pixelvergleichsdaten bleiben als nicht verfügbar erkennbar.
def _clipping_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    geometric = sum(bool(row["geometric_outside"]) for row in rows)
    pixel = sum(row["pixel_comparison_error"] is not None for row in rows)
    return {
        "geometric_outside_box_count": geometric,
        "geometric_outside_share": geometric / len(rows) if rows else 0.0,
        "pixel_comparison_error_count": pixel,
        "pixel_comparison_available": pixel > 0,
    }


# Input: Runzeilen mit Overlapzählungen.
# Output: Anzahl und Anteil überlappender Bounding-Box-Paare.
# Die Paarbasis zählt alle achsenparallelen Boxpaare innerhalb ausgewerteter Runs.
def _overlap_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    overlap = sum(int(row["overlap_pair_count"]) for row in rows)
    total = sum(int(row["overlap_pair_total"]) for row in rows)
    return {
        "overlap_pair_count": overlap,
        "overlap_pair_total": total,
        "overlap_pair_share": overlap / total if total else 0.0,
        "definition": (
            "achsenparallele Bounding-Box-Paare; kein Masken- oder Polygon-Overlap"
        ),
    }


# Input: Runzeilen.
# Output: Konfigurationen mit Anzahl beider Modi und Balance-Flag.
# Ein Gruppenvergleich ist nur bei vollständigem Konfigurationsschlüssel sinnvoll.
def _configuration_summaries(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, ...], Counter[str]] = defaultdict(Counter)
    for row in rows:
        groups[_configuration_key(row)][str(row.get("placement_mode", ""))] += 1
    return [
        {
            "configuration": _configuration_dict(key),
            "run_counts": {mode: counts.get(mode, 0) for mode in ("corners", "free")},
            "balanced": counts.get("corners", 0) == counts.get("free", 0),
        }
        for key, counts in sorted(groups.items())
    ]


# Input: Runzeilen.
# Output: Vollständige und balancierte Konfigurationen, die beide Modi enthalten.
# Unbalancierte Gruppen sind für globale Vergleiche ausgeschlossen.
def _comparable_configuration_keys(
    rows: Sequence[Mapping[str, Any]],
) -> set[tuple[str, ...]]:
    modes: dict[tuple[str, ...], set[str]] = defaultdict(set)
    counts: dict[tuple[str, ...], Counter[str]] = defaultdict(Counter)
    for row in rows:
        key = _configuration_key(row)
        mode = str(row.get("placement_mode", ""))
        modes[key].add(mode)
        counts[key][mode] += 1
    return {
        key
        for key in modes
        if {"corners", "free"} <= modes[key]
        and all(key)
        and counts[key]["corners"] == counts[key]["free"]
    }


# Input: Run- oder Boxzeile mit Konfigurationsfeldern.
# Output: Stabiler Vergleichsschlüssel aus Rotation, Dokumenttyp, Maßen und Rendering.
def _configuration_key(row: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(
        str(row.get(key, ""))
        for key in ("rotation", "document_type", "width", "height", "font", "font_size")
    )


# Input: Konfigurationsschlüssel.
# Output: JSON-kompatibles Konfigurationsmapping.
def _configuration_dict(key: Sequence[str]) -> dict[str, str]:
    return dict(
        zip(
            ("rotation", "document_type", "width", "height", "font", "font_size"),
            key,
            strict=True,
        )
    )


# Input: Boxzeilen, Plotpfad, Binning und freigegebene Konfigurationen.
# Output: Relative Plotpfade; fehlendes Matplotlib verhindert keine Tabellenanalyse.
# Heatmaps je Modus teilen Range, Bins und eine aus beiden Modi abgeleitete Farbskala.
def _write_plots(
    rows: Sequence[dict[str, Any]],
    path: Path,
    bins: int,
    comparable_keys: set[tuple[str, ...]],
) -> list[str]:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return []
    path.mkdir(parents=True, exist_ok=True)
    plot_files: list[str] = []
    modes = ("corners", "free")
    grouped: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[_configuration_key(row)].append(row)
    for index, (configuration, configuration_rows) in enumerate(
        sorted(grouped.items())
    ):
        config_path = path / f"config_{index:03d}"
        config_path.mkdir(parents=True, exist_ok=True)
        for mode in modes:
            selected = [
                row for row in configuration_rows if row["placement_mode"] == mode
            ]
            if not selected:
                continue
            plot_files.extend(
                _write_mode_plots(
                    selected, config_path, bins, mode, f"plots/config_{index:03d}"
                )
            )
        (config_path / "summary.json").write_text(
            json.dumps(
                {
                    "configuration": _configuration_dict(configuration),
                    "run_count": len(
                        {str(row["run_id"]) for row in configuration_rows}
                    ),
                    "box_count": len(configuration_rows),
                    "mode_counts": dict(
                        Counter(
                            str(row["placement_mode"]) for row in configuration_rows
                        )
                    ),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        plot_files.append(f"plots/config_{index:03d}/summary.json")
    common_rows = [row for row in rows if _configuration_key(row) in comparable_keys]
    heatmap = heatmap_parameters(rows, comparable_keys, bins)
    matrices = [heatmap["counts"][mode] for mode in modes]
    shared_vmax = int(heatmap["vmax"])
    for mode, matrix in zip(modes, matrices, strict=True):
        selected = [
            row
            for row in (common_rows if comparable_keys else rows)
            if row["placement_mode"] == mode
        ]
        separate = not comparable_keys
        matrix_max = max((cell for line in matrix for cell in line), default=0)
        fig, axis = plt.subplots()
        image = axis.imshow(
            matrix,
            origin="lower",
            extent=(0, 1, 0, 1),
            vmin=0,
            vmax=max(shared_vmax, matrix_max, 1),
            aspect="auto",
        )
        fig.colorbar(image, ax=axis)
        note = (
            "separate descriptive view"
            if separate
            else "shared comparable configurations"
        )
        axis.set(
            xlim=(0, 1),
            ylim=(0, 1),
            xlabel="center_x",
            ylabel="center_y",
            title=f"Mittelpunkt-Heatmap: {mode} (n={len(selected)}; {note})",
        )
        target = path / f"center_heatmap_{mode}.png"
        fig.savefig(target, dpi=140, bbox_inches="tight")
        plt.close(fig)
        plot_files.append(f"plots/{target.name}")
    if not comparable_keys:
        return plot_files
    plot_files.extend(_write_global_plots(common_rows, path, bins))
    return plot_files


# Input: Boxzeilen eines Modus, Plotpfad, Binning und Modusname.
# Output: Relative Pfade für vollständige getrennte Modusplots.
# Histogramme, Boxplots, Scatterplot und Regionen tragen die jeweilige Stichprobengröße.
def _write_mode_plots(
    rows: Sequence[Mapping[str, Any]],
    path: Path,
    bins: int,
    mode: str,
    relative_prefix: str,
) -> list[str]:
    import matplotlib.pyplot as plt

    path.mkdir(parents=True, exist_ok=True)
    files: list[str] = []
    for field in ("center_x", "center_y", "edge_distance"):
        figure, axis = plt.subplots()
        axis.hist([float(row[field]) for row in rows], bins=bins, range=(0, 1))
        axis.set_title(f"{field}: {mode} (n={len(rows)})")
        target = path / f"hist_{field}_{mode}.png"
        figure.savefig(target, dpi=140, bbox_inches="tight")
        plt.close(figure)
        files.append(f"{relative_prefix}/{target.name}")
    for field in ("normalized_width", "normalized_height", "normalized_area"):
        figure, axis = plt.subplots()
        axis.boxplot([float(row[field]) for row in rows])
        axis.set_title(f"{field}: {mode} (n={len(rows)})")
        target = path / f"boxplot_{field}_{mode}.png"
        figure.savefig(target, dpi=140, bbox_inches="tight")
        plt.close(figure)
        files.append(f"{relative_prefix}/{target.name}")
    figure, axis = plt.subplots()
    axis.scatter(
        [float(row["center_x"]) for row in rows],
        [float(row["center_y"]) for row in rows],
    )
    axis.set(xlim=(0, 1), ylim=(0, 1), xlabel="center_x", ylabel="center_y")
    axis.set_title(f"Mittelpunkt: {mode} (n={len(rows)})")
    target = path / f"scatter_centers_{mode}.png"
    figure.savefig(target, dpi=140, bbox_inches="tight")
    plt.close(figure)
    files.append(f"{relative_prefix}/{target.name}")
    return files


# Input: Boxzeilen freigegebener Konfigurationen, Plotpfad und Binning.
# Output: Relative Pfade für globale Histogramme, Boxplots und Scatterplot.
# Die globale Plotfamilie enthält ausschließlich die im Manifest
# genannten Konfigurationen.
def _write_global_plots(
    rows: Sequence[Mapping[str, Any]], path: Path, bins: int
) -> list[str]:
    import matplotlib.pyplot as plt

    files: list[str] = []
    modes = ("corners", "free")
    for field in ("center_x", "center_y", "edge_distance"):
        figure, axis = plt.subplots()
        for mode in modes:
            hist_values = [
                float(row[field]) for row in rows if row["placement_mode"] == mode
            ]
            axis.hist(
                hist_values,
                bins=bins,
                range=(0, 1),
                alpha=0.45,
                label=f"{mode} (n={len(hist_values)})",
            )
        axis.legend()
        axis.set(title=f"{field} (vergleichbare Konfigurationen)", xlabel=field)
        target = path / f"hist_{field}.png"
        figure.savefig(target, dpi=140, bbox_inches="tight")
        plt.close(figure)
        files.append(f"plots/{target.name}")
    for field in ("normalized_width", "normalized_height", "normalized_area"):
        figure, axis = plt.subplots()
        box_values: list[list[float]] = [
            [float(row[field]) for row in rows if row["placement_mode"] == mode]
            for mode in modes
        ]
        axis.boxplot(box_values)
        axis.set_xticks(
            (1, 2),
            labels=[
                mode + " (n=" + str(len(box_values[index])) + ")"
                for index, mode in enumerate(modes)
            ],
        )
        axis.set_title(f"{field} (vergleichbare Konfigurationen)")
        target = path / f"boxplot_{field}.png"
        figure.savefig(target, dpi=140, bbox_inches="tight")
        plt.close(figure)
        files.append(f"plots/{target.name}")
    figure, axis = plt.subplots()
    for mode in modes:
        selected = [row for row in rows if row["placement_mode"] == mode]
        axis.scatter(
            [float(row["center_x"]) for row in selected],
            [float(row["center_y"]) for row in selected],
            label=f"{mode} (n={len(selected)})",
        )
    axis.set(xlim=(0, 1), ylim=(0, 1), xlabel="center_x", ylabel="center_y")
    axis.legend()
    axis.set_title("Mittelpunkt-Scatter (vergleichbare Konfigurationen)")
    target = path / "scatter_centers.png"
    figure.savefig(target, dpi=140, bbox_inches="tight")
    plt.close(figure)
    files.append(f"plots/{target.name}")
    return files


# Input: Boxzeilen eines Modus und Binning.
# Output: Quadratische Häufigkeitsmatrix mit gemeinsamer `[0,1]`-Skala.
# Die Matrix ist unabhängig von NumPy und deterministisch reproduzierbar.
def _histogram_counts(rows: Sequence[Mapping[str, Any]], bins: int) -> list[list[int]]:
    result = [[0 for _ in range(bins)] for _ in range(bins)]
    for row in rows:
        x, y = float(row["center_x"]), float(row["center_y"])
        result[min(bins - 1, max(0, int(y * bins)))][
            min(bins - 1, max(0, int(x * bins)))
        ] += 1
    return result


# Input: Boxzeilen, freigegebene Konfigurationen und Binning.
# Output: Gemeinsame Heatmap-Counts, Achsenbereich, Bins und Farbobergrenze.
# Beide Modi verwenden exakt dieselben Parameter; ohne Vergleichssatz werden
# alle Daten deskriptiv dargestellt.
def heatmap_parameters(
    rows: Sequence[Mapping[str, Any]],
    comparable_keys: set[tuple[str, ...]],
    bins: int,
) -> dict[str, Any]:
    if bins <= 0:
        raise ValueError("bins muss positiv sein.")
    selected = [row for row in rows if _configuration_key(row) in comparable_keys]
    if not comparable_keys:
        selected = list(rows)
    counts = {
        mode: _histogram_counts(
            [row for row in selected if row["placement_mode"] == mode], bins
        )
        for mode in ("corners", "free")
    }
    vmax = max(
        (cell for matrix in counts.values() for line in matrix for cell in line),
        default=0,
    )
    return {
        "counts": counts,
        "bins": bins,
        "range": ((0.0, 1.0), (0.0, 1.0)),
        "vmax": vmax,
        "comparable": bool(comparable_keys),
        "sample_count": len(selected),
    }


# Input: Datei mit Ground Truth.
# Output: SHA-256-Fingerprint der Eingabedatei oder ein `unavailable:`-Wert.
# Der Fingerprint verhindert, dass Pfadkopien als unterschiedliche Inputs gelten.
def input_fingerprint(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return f"unavailable:{path.as_posix()}"


# Input: Ground-Truth-Pfad, Payload, Dimensionen und Boxmetriken.
# Output: Stabiler Run-Fingerprint über alle fachlich relevanten Felder.
# Der Fingerprint ist unabhängig vom `run_id` und dedupliziert deterministische Kopien.
def run_fingerprint(
    path: Path,
    payload: Mapping[str, Any],
    width: float,
    height: float,
    rows: Sequence[Mapping[str, Any]],
) -> str:
    geometry = [
        [
            float(row["left"]),
            float(row["top"]),
            float(row["right"]),
            float(row["bottom"]),
        ]
        for row in rows
    ]
    values = {
        "seed": _metadata(payload, {}, ("seed",)),
        "placement_mode": _metadata(payload, {}, ("placement_mode",), "unknown"),
        "input_fingerprint": _metadata(
            payload, {}, ("input_fingerprint",), input_fingerprint(path)
        ),
        "rotation": _metadata(payload, {}, ("rotation", "rotation_degrees")),
        "document_type": _metadata(payload, {}, ("document_type",), "unknown"),
        "width": width,
        "height": height,
        "font": _metadata(
            payload, {}, ("font", "font_family", "effective_font_family")
        ),
        "font_size": _metadata(payload, {}, ("font_size", "font_size_pct")),
        "box_geometry": geometry,
    }
    return hashlib.sha256(
        json.dumps(values, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


# Input: Rekursives Eingabeverzeichnis und Analyseoptionen.
# Output: Neuer Analysepfad; fehlerhafte und übersprungene Runs bleiben im Manifest.
# Rohdateien werden ausschließlich gelesen und niemals überschrieben.
def analyze_paths(
    input_path: Path,
    output_dir: Path,
    analysis_name: str,
    bins: int,
    width: float | None = None,
    height: float | None = None,
) -> Path:
    paths = (
        sorted(input_path.rglob("ground_truth.json"))
        if input_path.is_dir()
        else [input_path]
    )
    payloads: list[tuple[Path, Mapping[str, Any]]] = []
    errors: list[dict[str, Any]] = []
    for path in paths:
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
            if isinstance(payload, Mapping):
                payloads.append((path, payload))
            else:
                errors.append(_skip(path, "invalid_payload", ["JSON-Objekt"]))
        except (OSError, json.JSONDecodeError, UnicodeError) as error:
            errors.append(_skip(path, "unreadable_ground_truth", [str(error)]))
    result = output_dir / analysis_name
    analyze_payloads(payloads, result, bins, width, height, errors)
    return result


# Input: Geladene Payloads, Zielpfad, Binning und Dimensionsfallback.
# Output: Keine Rückgabe; schreibt deduplizierte Analyseartefakte und Skip-Manifest.
# Exakte Wiederholungen bleiben als Rohdateien erhalten, zählen aber nur einmal.
def analyze_payloads(
    payloads: Sequence[tuple[Path, Mapping[str, Any]]],
    output_dir: Path,
    bins: int,
    width: float | None = None,
    height: float | None = None,
    errors: Sequence[Mapping[str, Any] | str] = (),
) -> None:
    if bins <= 0:
        raise ValueError("bins muss positiv sein.")
    candidates: list[dict[str, Any]] = []
    skipped = [_skip_from_value(error) for error in errors]
    for path, payload in payloads:
        dimensions = image_dimensions_with_source(path, payload, width, height)
        annotations = payload.get("box_annotations", [])
        if dimensions["width"] is None:
            skipped.append(
                _skip(
                    path,
                    "missing_dimensions",
                    dimensions.get(
                        "missing_information",
                        ["preview/output_file/source_file/fallback"],
                    ),
                )
            )
            continue
        if not isinstance(annotations, list):
            skipped.append(
                _skip(path, "invalid_annotations", ["box_annotations ist keine Liste"])
            )
            continue
        rows, annotation_skips = _validated_annotation_rows(
            path,
            payload,
            annotations,
            float(dimensions["width"]),
            float(dimensions["height"]),
            str(dimensions["source"]),
        )
        skipped.extend(annotation_skips)
        if not rows:
            skipped.append(
                _skip(path, "no_valid_boxes", ["keine Annotation mit corners"])
            )
            continue
        fingerprint = run_fingerprint(
            path, payload, float(dimensions["width"]), float(dimensions["height"]), rows
        )
        for row in rows:
            row["run_fingerprint"] = fingerprint
        candidates.append(
            {
                "path": path.as_posix(),
                "fingerprint": fingerprint,
                "rows": rows,
                "run": summarize_run(rows),
            }
        )
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        grouped[candidate["fingerprint"]].append(candidate)
    unique = [items[0] for items in grouped.values()]
    duplicate_runs = [
        {
            "run_fingerprint": key,
            "files": [item["path"] for item in items],
            "kept": items[0]["path"],
        }
        for key, items in sorted(grouped.items())
        if len(items) > 1
    ]
    box_rows = [row for item in unique for row in item["rows"]]
    run_rows = [item["run"] for item in unique]
    manifest = {
        "found_run_count": len(payloads),
        "candidate_run_count": len(candidates),
        "unique_run_count": len(unique),
        "duplicate_run_count": len(candidates) - len(unique),
        "duplicate_runs": duplicate_runs,
        "skipped_runs": skipped,
        "evaluated_run_count": len(run_rows),
        "evaluated_box_count": len(box_rows),
        "modes": sorted({str(row["placement_mode"]) for row in box_rows}),
        "unbalanced_groups": _unbalanced_groups(run_rows),
    }
    write_analysis_outputs(box_rows, run_rows, output_dir, manifest, bins)


# Input: Ground-Truth-Pfad, Payload, Annotationliste, Bildmaße und Dimensionsquelle.
# Output: Robuste Boxzeilen und ein Skip-Objekt je ungültiger Annotation.
# Fehler werden mit Originalindex protokolliert; gültige Annotationen desselben
# Runs bleiben auswertbar.
def _validated_annotation_rows(
    path: Path,
    payload: Mapping[str, Any],
    annotations: list[Any],
    width: float,
    height: float,
    dimension_source: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for index, annotation in enumerate(annotations):
        if not isinstance(annotation, Mapping):
            skipped.append(
                _annotation_skip(
                    path, index, "invalid_annotation", ["Mapping", "corners"]
                )
            )
            continue
        if "corners" not in annotation:
            skipped.append(
                _annotation_skip(path, index, "missing_corners", ["corners"])
            )
            continue
        try:
            rows.append(
                extract_box_metrics(
                    path, payload, width, height, annotation, index, dimension_source
                )
            )
        except (KeyError, TypeError, ValueError) as error:
            skipped.append(
                _annotation_skip(path, index, "invalid_corners", [str(error)])
            )
    return rows, skipped


# Input: Ground-Truth-Pfad, Annotationindex, Grund und fehlende Informationen.
# Output: Auditierbares Skip-Objekt für eine einzelne Annotation.
# Der Pfad und der Originalindex ermöglichen die Rückverfolgung zur Rohdatei.
def _annotation_skip(
    path: Path, index: int, reason: str, missing_information: Sequence[str]
) -> dict[str, Any]:
    result = _skip(path, reason, missing_information)
    result["annotation_index"] = index
    return result


# Input: Pfad und Grund mit fehlenden Informationen.
# Output: Einheitliches auditierbares Skip-Objekt.
def _skip(
    path: Path, reason: str, missing_information: Sequence[str]
) -> dict[str, Any]:
    return {
        "path": path.as_posix(),
        "reason": reason,
        "missing_information": list(missing_information),
    }


# Input: String- oder Mapping-Fehler aus dem Aufrufer.
# Output: Normalisiertes Skip-Objekt.
def _skip_from_value(value: Mapping[str, Any] | str) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {
        "path": "<preload>",
        "reason": "input_error",
        "missing_information": [value],
    }


# Input: Runzeilen.
# Output: Konfigurationen mit ungleichen `corners`-/`free`-Runzahlen.
# Die Zählung erfolgt anhand der deduplizierten Runzeilen.
def _unbalanced_groups(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, ...], Counter[str]] = defaultdict(Counter)
    for row in rows:
        key = _configuration_key(row)
        groups[key][str(row.get("placement_mode", ""))] += 1
    return [
        {
            "configuration": _configuration_dict(key),
            "run_counts": {mode: counts.get(mode, 0) for mode in ("corners", "free")},
        }
        for key, counts in sorted(groups.items())
        if counts.get("corners", 0) != counts.get("free", 0)
    ]
