"""Formatbewusste Vergleiche fuer qualitative Evaluationspruefungen."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

from pydicom.errors import InvalidDicomError

from .case_outcomes import CaseProfile, ProfileStatus


def file_sha256(path: Path) -> str:
    """Berechnet einen Datei-Fingerprint."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalized_json_equal(left: Path, right: Path) -> bool:
    """Vergleicht JSON semantisch und ignoriert Formatierung sowie Newlines."""
    left_payload: Any = json.loads(left.read_text(encoding="utf-8-sig"))
    right_payload: Any = json.loads(right.read_text(encoding="utf-8-sig"))
    return bool(_normalize_json(left_payload) == _normalize_json(right_payload))


# Input: JSON-kompatibler Wert.
# Output: JSON-Wert mit workspaceunabhaengigen Artefaktpfaden.
def _normalize_json(value: Any, key: str = "") -> Any:
    if isinstance(value, dict):
        return {name: _normalize_json(item, name) for name, item in value.items()}
    if isinstance(value, list):
        return [_normalize_json(item, key) for item in value]
    if isinstance(value, str) and (
        "file" in key.casefold() or "path" in key.casefold()
    ):
        return Path(value).name
    return value


def decoded_raster_equal(left: Path, right: Path, tolerance: int = 0) -> bool:
    """Vergleicht dekodierte JPG/PNG-Pixel mit einer ganzzahligen Toleranz."""
    from PIL import Image, ImageChops

    with Image.open(left) as first, Image.open(right) as second:
        if first.size != second.size:
            return False
        difference = ImageChops.difference(first.convert("RGB"), second.convert("RGB"))
        extrema = difference.getextrema()
        maxima = [value[1] if isinstance(value, tuple) else value for value in extrema]
        return difference.getbbox() is None or max(maxima) <= tolerance


# Input: zwei Rasterbilder und eine erlaubte Injektions-ROI.
# Output: Gleichheit aller Pixel ausserhalb der ROI.
def decoded_raster_equal_outside_roi(
    left: Path, right: Path, roi: tuple[int, int, int, int], tolerance: int = 0
) -> bool:
    """Vergleicht Rasterdaten ausserhalb der erlaubten Region."""
    from PIL import Image, ImageChops

    with Image.open(left) as first, Image.open(right) as second:
        if first.size != second.size:
            return False
        difference = ImageChops.difference(
            first.convert("RGB"), second.convert("RGB")
        ).convert("L")
        mask = Image.new("L", difference.size, 255)
        mask.paste(0, roi)
        if tolerance:
            difference = difference.point(
                lambda value: 0 if value <= tolerance else value
            )
        return ImageChops.multiply(difference, mask).getbbox() is None


# Input: DICOM-Dateien, Allowlist und optionale erlaubte Konvertierungen.
# Output: Semantischer Pixelvergleich ausserhalb einer ROI.
# Der Vergleich arbeitet auf dekodierten Frames und nicht auf Containerbytes.
def dicom_pixels_equal(
    left: Path,
    right: Path,
    roi: tuple[int, int, int, int] | None = None,
    tolerance: int = 0,
) -> dict[str, Any]:
    """Vergleicht DICOM-Pixel inklusive aller spaeteren Multiframe-Frames."""
    import numpy as np
    import pydicom

    try:
        first = pydicom.dcmread(left)
        second = pydicom.dcmread(right)
        a, b = first.pixel_array, second.pixel_array
        if a.shape != b.shape:
            return {"status": "different", "reason": "Pixel-Shape unterscheidet sich"}
        if roi is None:
            equal = bool(
                np.max(np.abs(a.astype(np.int64) - b.astype(np.int64))) <= tolerance
            )
        else:
            x1, y1, x2, y2 = roi
            mask = np.ones(a.shape[-2:], dtype=bool)
            mask[y1:y2, x1:x2] = False
            equal = not mask.any() or bool(
                np.max(
                    np.abs(
                        a[..., mask].astype(np.int64) - b[..., mask].astype(np.int64)
                    )
                )
                <= tolerance
            )
        return {"status": "same" if equal else "different"}
    except (InvalidDicomError, OSError, EOFError, ValueError, AttributeError) as error:
        return {"status": "unavailable", "reason": str(error)}


# Input: unveraenderte Quelle, erzeugtes Dokument und optionale Injektions-ROI.
# Output: Formatbewusster Input/Output-Vergleich mit explizitem Status.
def compare_input_output(
    source: Path,
    output: Path,
    *,
    roi: tuple[int, int, int, int] | dict[int, tuple[int, int, int, int]] | None = None,
    allowlist: set[int] | None = None,
    tolerance: int = 0,
) -> dict[str, Any]:
    """Prueft, dass nur erlaubte Injektionsaenderungen entstanden sind."""
    suffix = source.suffix.casefold()
    if suffix != output.suffix.casefold():
        return {"status": "different", "reason": "Format unterscheidet sich"}
    try:
        if suffix == ".pdf" and shutil.which("pdftoppm") is None:
            return {"status": "unavailable", "reason": "pdftoppm nicht verfuegbar"}
        if suffix == ".dcm":
            if isinstance(roi, dict):
                return {
                    "status": "unavailable",
                    "reason": "DICOM-ROI ist nicht seitenbezogen",
                }
            attributes = compare_dicom_attributes(
                source, output, allowlist or {0x00020010}
            )
            pixels_equal = dicom_pixels_equal(
                source, output, roi=roi, tolerance=tolerance
            )
            if attributes["status"] == "unavailable":
                return attributes
            if pixels_equal["status"] == "unavailable":
                return pixels_equal
            return {
                "status": "same"
                if attributes["status"] == "same" and pixels_equal["status"] == "same"
                else "different",
                "metadata_differences": attributes.get("metadata_differences", []),
                "pixels_outside_roi_equal": pixels_equal["status"] == "same",
            }
        if suffix in {".jpg", ".jpeg", ".png"}:
            if isinstance(roi, dict):
                return {
                    "status": "unavailable",
                    "reason": "Raster-ROI ist nicht seitenbezogen",
                }
            equal = (
                decoded_raster_equal(source, output, tolerance)
                if roi is None
                else decoded_raster_equal_outside_roi(source, output, roi, tolerance)
            )
            return {
                "status": "same" if equal else "different",
                "roi_checked": roi is not None,
            }
        if suffix == ".pdf":
            equal = _compare_pdf_outputs(source, output, tolerance, roi=roi)
            return {
                "status": "same" if equal else "different",
                "pages_checked": _pdf_page_count(source),
                "roi_checked": roi is not None,
            }
        return {"status": "unsupported", "reason": f"Format {suffix or '<leer>'}"}
    except FileNotFoundError as error:
        return {"status": "unavailable", "reason": str(error)}
    except (
        OSError,
        EOFError,
        ValueError,
        TypeError,
        KeyError,
        IndexError,
        InvalidDicomError,
    ) as error:
        return {"status": "unavailable", "reason": str(error)}


# Input: Ground-Truth-Annotationen.
# Output: Konservative Union der Injektionsregionen als Pixel-ROI.
def _annotation_roi(payload: dict[str, Any]) -> tuple[int, int, int, int] | None:
    boxes = payload.get("box_annotations")
    if not isinstance(boxes, list) or not boxes:
        return None
    points: list[tuple[float, float]] = []
    for annotation in boxes:
        if not isinstance(annotation, dict):
            continue
        corners = annotation.get("corners")
        if isinstance(corners, list):
            for point in corners:
                if (
                    isinstance(point, dict)
                    and isinstance(point.get("x"), (int, float))
                    and isinstance(point.get("y"), (int, float))
                ):
                    points.append((float(point["x"]), float(point["y"])))
    if not points:
        return None
    return (
        max(0, int(min(point[0] for point in points))),
        max(0, int(min(point[1] for point in points))),
        int(max(point[0] for point in points)) + 1,
        int(max(point[1] for point in points)) + 1,
    )


# Input: Ground-Truth-Annotationen mit frame_index/page index.
# Output: Seitenbezogene Injektions-ROIs; fehlende Seiten bleiben unbekannt.
def _annotation_rois_by_page(
    payload: dict[str, Any],
) -> dict[int, tuple[int, int, int, int]] | None:
    boxes = payload.get("box_annotations")
    if not isinstance(boxes, list):
        return None
    grouped: dict[int, list[tuple[float, float]]] = {}
    for annotation in boxes:
        if not isinstance(annotation, dict):
            continue
        page = annotation.get("frame_index", 0)
        if not isinstance(page, int) or page < 0:
            return None
        corners = annotation.get("corners")
        if not isinstance(corners, list):
            continue
        for point in corners:
            if (
                isinstance(point, dict)
                and isinstance(point.get("x"), (int, float))
                and isinstance(point.get("y"), (int, float))
            ):
                grouped.setdefault(page, []).append(
                    (float(point["x"]), float(point["y"]))
                )
    if not grouped:
        return None
    return {
        page: (
            max(0, int(min(point[0] for point in points))),
            max(0, int(min(point[1] for point in points))),
            int(max(point[0] for point in points)) + 1,
            int(max(point[1] for point in points)) + 1,
        )
        for page, points in grouped.items()
        if points
    }


# Input: referenzierter Artefaktwert und Bundle-Root.
# Output: Aufgeloester Pfad fuer relative und absolute Ground-Truth-Werte.
def _resolve_artifact(value: Any, bundle: Path) -> Path:
    path = Path(str(value))
    return path if path.is_absolute() else bundle / path


# Input: zwei komplette Evaluationslaeufe mit JSON-/Raster-/DICOM-Artefakten.
# Output: stabile boolesche Semantikpruefung.
# Pfade und Containerformatierung werden ignoriert; Identitaet und Geometrie
# werden ueber normalisierte Ground-Truth-JSONs verglichen.
def compare_run_semantics(left_run: Path, right_run: Path, tolerance: int = 0) -> bool:
    """Vergleicht Ground Truth und dekodierte Ausgabedokumente zweier Runs."""
    return compare_evaluation_runs(left_run, right_run, tolerance)


def compare_dicom_attributes(
    left: Path, right: Path, allowlist: set[int] | None = None
) -> dict[str, Any]:
    """Meldet unterschiedliche DICOM-Tags ausserhalb einer Allowlist."""
    import pydicom

    allowed = allowlist or set()
    try:
        first = pydicom.dcmread(left, stop_before_pixels=True)
        second = pydicom.dcmread(right, stop_before_pixels=True)
        tags = set(first.keys()) | set(second.keys())
        differences = sorted(
            int(tag)
            for tag in tags
            if int(tag) not in allowed and first.get(tag) != second.get(tag)
        )
        return {
            "status": "same" if not differences else "different",
            "metadata_differences": differences,
        }
    except (InvalidDicomError, OSError, EOFError, ValueError) as error:
        return {"status": "unavailable", "reason": str(error)}


def profile_from_payload(
    payload: dict[str, Any], case_id: str, source_fingerprint: str
) -> dict[str, Any]:
    """Extrahiert stabile Profilfelder aus einem optionalen Payload."""
    return {
        "case_id": case_id,
        "source_fingerprint": source_fingerprint,
        **{
            key: payload.get(key)
            for key in (
                "document_type",
                "photometry",
                "width",
                "height",
                "size_class",
                "frame_mode",
                "placement_mode",
                "rotation_degrees",
                "font_or_renderer",
                "profile_status",
                "profile_reason",
                "expected_schema_fields",
                "present_structured_fields",
                "used_structured_fields",
                "missing_expected_fields",
            )
        },
    }


def profile_source(
    path: Path,
    case_id: str,
    expected_schema_fields: tuple[str, ...] = (),
    used_schema_fields: tuple[str, ...] = (),
    *,
    placement_mode: str | None = None,
    rotation_degrees: int | None = None,
    font_or_renderer: str | None = None,
    handwriting_options: dict[str, Any] | None = None,
    render_options: dict[str, Any] | None = None,
) -> CaseProfile:
    """Profiling einer DICOM-, JPG- oder PDF-Quelle mit explizitem Status."""
    try:
        fingerprint = file_sha256(path)
    except OSError:
        return CaseProfile(
            case_id=case_id,
            source_fingerprint=f"unavailable:{path.as_posix()}",
            document_type=path.suffix.casefold().lstrip(".") or None,
            expected_schema_fields=expected_schema_fields,
            used_structured_fields=used_schema_fields,
            missing_expected_fields=expected_schema_fields,
            profile_status=ProfileStatus.UNAVAILABLE,
            profile_reason="Quelle fehlt oder ist nicht lesbar",
            placement_mode=placement_mode,
            rotation_degrees=rotation_degrees,
            font_or_renderer=font_or_renderer,
            handwriting_options=handwriting_options or {},
            render_options=render_options or {},
        )
    present: tuple[str, ...] = ()
    missing = tuple(expected_schema_fields)
    try:
        if path.suffix.casefold() == ".dcm":
            import pydicom

            dataset = pydicom.dcmread(path, stop_before_pixels=True)
            photometry = str(getattr(dataset, "PhotometricInterpretation", "")).upper()
            samples = int(getattr(dataset, "SamplesPerPixel", 1))
            supported = photometry in {"MONOCHROME2", "RGB", "YBR_FULL_422"}
            supported = supported and not (
                photometry in {"RGB", "YBR_FULL_422"} and samples != 3
            )
            supported = supported and not (photometry == "MONOCHROME2" and samples != 1)
            support_reason = (
                None if supported else "DICOM-Repraesentation nicht unterstuetzt"
            )
            present = tuple(
                field
                for field in expected_schema_fields
                if _dicom_field_value(dataset, field) not in (None, "")
            )
            missing = tuple(
                field for field in expected_schema_fields if field not in present
            )
            return CaseProfile(
                case_id=case_id,
                source_fingerprint=fingerprint,
                document_type="dcm",
                photometry=str(getattr(dataset, "PhotometricInterpretation", "")),
                width=int(getattr(dataset, "Columns", 0)) or None,
                height=int(getattr(dataset, "Rows", 0)) or None,
                size_class=_size_class(
                    int(getattr(dataset, "Columns", 0)),
                    int(getattr(dataset, "Rows", 0)),
                ),
                frame_mode="multiframe"
                if int(getattr(dataset, "NumberOfFrames", 1)) > 1
                else "singleframe",
                supported=supported,
                expected_schema_fields=expected_schema_fields,
                present_structured_fields=present,
                used_structured_fields=used_schema_fields,
                missing_expected_fields=missing,
                profile_status=ProfileStatus.COMPLETE
                if not missing
                else ProfileStatus.PARTIAL,
                profile_reason=(
                    support_reason
                    or (
                        None if not missing else "Erwartete strukturierte Felder fehlen"
                    )
                ),
                placement_mode=placement_mode,
                rotation_degrees=rotation_degrees,
                font_or_renderer=font_or_renderer,
                handwriting_options=handwriting_options or {},
                render_options=render_options or {},
            )
        if path.suffix.casefold() == ".pdf":
            from pypdf import PdfReader

            reader = PdfReader(str(path))
            pages = len(reader.pages)
            return CaseProfile(
                case_id=case_id,
                source_fingerprint=fingerprint,
                document_type="pdf",
                frame_mode="multiframe" if pages > 1 else "singleframe",
                supported=True,
                profile_status=ProfileStatus.COMPLETE,
                profile_reason=f"{pages} PDF-Seite(n)",
                expected_schema_fields=expected_schema_fields,
                used_structured_fields=used_schema_fields,
                placement_mode=placement_mode,
                rotation_degrees=rotation_degrees,
                font_or_renderer=font_or_renderer,
                handwriting_options=handwriting_options or {},
                render_options=render_options or {},
            )
        suffix = path.suffix.casefold()
        if suffix not in {".jpg", ".jpeg"}:
            return CaseProfile(
                case_id=case_id,
                source_fingerprint=fingerprint,
                document_type=suffix.lstrip(".") or None,
                expected_schema_fields=expected_schema_fields,
                used_structured_fields=used_schema_fields,
                missing_expected_fields=expected_schema_fields,
                profile_status=ProfileStatus.UNAVAILABLE,
                profile_reason="Dateiformat nicht unterstuetzt",
                placement_mode=placement_mode,
                rotation_degrees=rotation_degrees,
                font_or_renderer=font_or_renderer,
                handwriting_options=handwriting_options or {},
                render_options=render_options or {},
            )
        from PIL import Image

        with Image.open(path) as image:
            return CaseProfile(
                case_id=case_id,
                source_fingerprint=fingerprint,
                document_type="jpg",
                width=image.width,
                height=image.height,
                frame_mode="singleframe",
                supported=True,
                size_class=_size_class(image.width, image.height),
                profile_status=ProfileStatus.COMPLETE,
                placement_mode=placement_mode,
                rotation_degrees=rotation_degrees,
                font_or_renderer=font_or_renderer,
                handwriting_options=handwriting_options or {},
                render_options=render_options or {},
            )
    except (OSError, EOFError, ValueError, TypeError, InvalidDicomError):
        return CaseProfile(
            case_id=case_id,
            source_fingerprint=fingerprint,
            document_type=path.suffix.casefold().lstrip(".") or None,
            expected_schema_fields=expected_schema_fields,
            used_structured_fields=used_schema_fields,
            missing_expected_fields=missing,
            profile_status=(
                ProfileStatus.NON_PARSEABLE
                if path.suffix.casefold() == ".dcm"
                else ProfileStatus.UNAVAILABLE
            ),
            profile_reason="Quelle konnte nicht geparst werden",
            placement_mode=placement_mode,
            rotation_degrees=rotation_degrees,
            font_or_renderer=font_or_renderer,
            handwriting_options=handwriting_options or {},
            render_options=render_options or {},
        )


# Input: Bildbreite und -hoehe.
# Output: Reproduzierbare Groessenklasse fuer Profilaggregate.
def _size_class(width: int, height: int) -> str:
    pixels = width * height
    if pixels <= 256 * 256:
        return "small"
    if pixels <= 1024 * 1024:
        return "medium"
    return "large"


# Input: DICOM-Dataset und schema field name oder DICOM-Keyword.
# Output: Wert des robust aufgeloesten DICOM-Feldes.
def _dicom_field_value(dataset: Any, field: str) -> Any:
    """Loest Schema-Namen sowohl als Keyword als auch ueber bekannte Tags auf."""
    value = getattr(dataset, field, None)
    if value is not None:
        return value
    keyword_map = {
        "patient_name": "PatientName",
        "patient_id": "PatientID",
        "patient_birth_date": "PatientBirthDate",
        "patient_sex": "PatientSex",
        "accession_number": "AccessionNumber",
    }
    return getattr(dataset, keyword_map.get(field, field), None)


# Input: zwei Evaluations-Bundles in getrennten Workspaces.
# Output: Semantischer Vergleich ohne workspaceabhaengige Pfade.
# Unbekannte Formate liefern keinen positiven Gleichheitsbefund.
def compare_evaluation_runs(
    left_run: Path, right_run: Path, tolerance: int = 0
) -> bool:
    """Vergleicht alle Bundle-Paare eines vollstaendigen Run-Verzeichnisses."""
    left_bundles = _discover_bundles(left_run)
    right_bundles = _discover_bundles(right_run)
    if len(left_bundles) != len(right_bundles):
        return False
    for left_bundle, right_bundle in zip(left_bundles, right_bundles, strict=True):
        if not _compare_bundle_pair(left_bundle, right_bundle, tolerance):
            return False
    return bool(left_bundles)


# Input: zwei Run-Roots mit bekannten Formaten.
# Output: Status und Grund der semantischen Vergleichbarkeit.
# Der Status unterscheidet Gleichheit, fachliche Differenz und Tool-Limitierungen.
def compare_evaluation_runs_detailed(
    left_run: Path, right_run: Path, tolerance: int = 0
) -> dict[str, Any]:
    left_bundles = _discover_bundles(left_run)
    right_bundles = _discover_bundles(right_run)
    if not left_bundles or len(left_bundles) != len(right_bundles):
        return {"status": "inconclusive", "reason": "Bundle-Anzahl unterscheidet sich"}
    for left_bundle, right_bundle in zip(left_bundles, right_bundles, strict=True):
        left_gt = left_bundle / "ground_truth.json"
        payload = json.loads(left_gt.read_text(encoding="utf-8-sig"))
        suffix = Path(str(payload.get("output_file", ""))).suffix.casefold()
        if suffix == ".pdf" and shutil.which("pdftoppm") is None:
            return {"status": "unavailable", "reason": "pdftoppm nicht verfuegbar"}
        if suffix not in {".dcm", ".jpg", ".jpeg", ".png", ".pdf"}:
            return {"status": "unsupported", "reason": f"Format {suffix or '<leer>'}"}
        if not _compare_bundle_pair(left_bundle, right_bundle, tolerance):
            return {"status": "different", "reason": f"Bundle {left_bundle.name}"}
    return {"status": "same", "bundle_count": len(left_bundles)}


# Input: zwei Bundle-Verzeichnisse und Rastertoleranz.
# Output: Boolescher Semantikstatus eines bekannten Formats.
def _compare_bundle_pair(left_run: Path, right_run: Path, tolerance: int) -> bool:
    left_gt, right_gt = left_run / "ground_truth.json", right_run / "ground_truth.json"
    if not left_gt.is_file() or not right_gt.is_file():
        return False
    left = json.loads(left_gt.read_text(encoding="utf-8-sig"))
    right = json.loads(right_gt.read_text(encoding="utf-8-sig"))
    if not isinstance(left, dict) or not isinstance(right, dict):
        return False
    if not normalized_json_equal(
        left_run / "ground_truth.json", right_run / "ground_truth.json"
    ):
        return False
    left_output = _resolve_artifact(left.get("output_file", ""), left_run)
    right_output = _resolve_artifact(right.get("output_file", ""), right_run)
    if left_output.suffix.casefold() != right_output.suffix.casefold():
        return False
    suffix = left_output.suffix.casefold()
    if suffix in {".jpg", ".jpeg", ".png"}:
        return decoded_raster_equal(left_output, right_output, tolerance)
    if suffix == ".dcm":
        roi = _annotation_roi(left)
        attributes = compare_dicom_attributes(left_output, right_output, {0x00020010})
        pixels = dicom_pixels_equal(
            left_output, right_output, roi=roi, tolerance=tolerance
        )
        return (
            str(attributes["status"]) == "same"
            and str(pixels["status"]) == "same"
        )
    if suffix == ".pdf":
        return _compare_pdf_outputs(
            left_output,
            right_output,
            tolerance,
            roi=_annotation_rois_by_page(left),
        )
    return False


# Input: zwei PDF-Dateien und Rastertoleranz.
# Output: Seitenweiser Vergleich oder False mit implizitem Tool-Limit.
# `pdftoppm` wird nur verwendet, wenn es lokal verfuegbar ist.
def _compare_pdf_outputs(
    left: Path,
    right: Path,
    tolerance: int,
    *,
    roi: tuple[int, int, int, int] | dict[int, tuple[int, int, int, int]] | None = None,
) -> bool:
    from tools.thesis_results.coordinate_validation.coordinate_validation import (
        render_pdf_page,
    )

    try:
        with tempfile.TemporaryDirectory(prefix="pdf-compare-") as directory:
            if _pdf_page_count(left) != _pdf_page_count(right):
                return False
            from pypdf import PdfReader

            left_reader = PdfReader(str(left))
            for page in range(_pdf_page_count(left)):
                left_png = Path(directory) / f"left-{page}.png"
                right_png = Path(directory) / f"right-{page}.png"
                render_pdf_page(left, page, 150, left_png)
                render_pdf_page(right, page, 150, right_png)
                page_roi = roi.get(page) if isinstance(roi, dict) else roi
                if isinstance(roi, dict) and page_roi is None:
                    return False
                scaled_roi = (
                    _scale_pdf_roi(page_roi, left_reader.pages[page], left_png)
                    if page_roi is not None
                    else None
                )
                equal = (
                    decoded_raster_equal(left_png, right_png, tolerance)
                    if page_roi is None
                    else decoded_raster_equal_outside_roi(
                        left_png,
                        right_png,
                        scaled_roi if scaled_roi is not None else page_roi,
                        tolerance,
                    )
                )
                if not equal:
                    return False
            return True
    except (OSError, RuntimeError, ValueError):
        return False


# Input: PDF-ROI in Punktkoordinaten, PDF-Seite und gerastertes Seitenbild.
# Output: Auf die konkrete Renderauflösung skalierte Pixel-ROI.
def _scale_pdf_roi(
    roi: tuple[int, int, int, int], page: Any, rendered: Path
) -> tuple[int, int, int, int]:
    from PIL import Image

    with Image.open(rendered) as image:
        width, height = image.size
    page_width = float(page.mediabox.width)
    page_height = float(page.mediabox.height)
    if page_width <= 0 or page_height <= 0:
        return roi
    sx, sy = width / page_width, height / page_height
    x1, y1, x2, y2 = roi
    # PDF-Koordinaten haben ihren Ursprung unten links, Rasterbilder oben links.
    raster_y1 = page_height - y2
    raster_y2 = page_height - y1
    return (
        max(0, round(x1 * sx)),
        max(0, round(raster_y1 * sy)),
        min(width, round(x2 * sx)),
        min(height, round(raster_y2 * sy)),
    )


# Input: PDF-Datei.
# Output: Anzahl parsbarer Seiten.
def _pdf_page_count(path: Path) -> int:
    from pypdf import PdfReader

    pages = len(PdfReader(str(path)).pages)
    if pages < 1:
        raise ValueError("PDF enthaelt keine Seiten")
    return pages


# Input: Run-Root oder einzelnes Bundle.
# Output: Stabil nach Bundlepfad sortierte Bundle-Liste.
def _discover_bundles(root: Path) -> list[Path]:
    if (root / "ground_truth.json").is_file():
        return [root]
    return sorted(
        path.parent for path in root.rglob("ground_truth.json") if path.is_file()
    )
