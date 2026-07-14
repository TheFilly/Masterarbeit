"""Factories for synthetic image documents used by integration tests."""

import json
from pathlib import Path

import numpy as np
from PIL import Image
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, SecondaryCaptureImageStorage

_SOP_INSTANCE_UID = "1.2.826.0.1.3680043.10.543.1"
_STUDY_INSTANCE_UID = "1.2.826.0.1.3680043.10.543.2"
_SERIES_INSTANCE_UID = "1.2.826.0.1.3680043.10.543.3"


# Input: `size` with the square image dimension.
# Output: RGB array containing a deterministic synthetic pattern.
# The pattern has enough contrast to expose one-pixel output changes.
def _synthetic_rgb_array(size: int = 256) -> np.ndarray:
    x_axis = np.arange(size, dtype=np.uint16)
    y_axis = x_axis[:, np.newaxis]
    red = np.broadcast_to((x_axis * 3) % 256, (size, size))
    green = np.broadcast_to((y_axis * 5) % 256, (size, size))
    blue = (x_axis[np.newaxis, :] + y_axis) % 256
    return np.stack((red, green, blue), axis=-1).astype(np.uint8)


# Input: `path` with the destination for the generated DICOM fixture.
# Output: The destination path after writing a synthetic RGB DICOM file.
# The fixture contains no patient-derived values or external binary assets.
def write_synthetic_dicom(path: Path) -> Path:
    pixels = _synthetic_rgb_array()
    file_meta = FileMetaDataset()
    file_meta.MediaStorageSOPClassUID = SecondaryCaptureImageStorage
    file_meta.MediaStorageSOPInstanceUID = _SOP_INSTANCE_UID
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    file_meta.ImplementationClassUID = "1.2.826.0.1.3680043.10.543.9"

    dataset = FileDataset(path.name, {}, file_meta=file_meta, preamble=b"\0" * 128)
    dataset.SOPClassUID = SecondaryCaptureImageStorage
    dataset.SOPInstanceUID = _SOP_INSTANCE_UID
    dataset.StudyInstanceUID = _STUDY_INSTANCE_UID
    dataset.SeriesInstanceUID = _SERIES_INSTANCE_UID
    dataset.Modality = "OT"
    dataset.PatientName = "SYNTHETIC^SOURCE"
    dataset.PatientID = "SYNTHETIC-SOURCE"
    dataset.Rows = pixels.shape[0]
    dataset.Columns = pixels.shape[1]
    dataset.SamplesPerPixel = 3
    dataset.PhotometricInterpretation = "RGB"
    dataset.PlanarConfiguration = 0
    dataset.BitsAllocated = 8
    dataset.BitsStored = 8
    dataset.HighBit = 7
    dataset.PixelRepresentation = 0
    dataset.PixelData = pixels.tobytes()
    dataset.save_as(path, enforce_file_format=True)
    return path


# Input: `path` with the destination for the generated JPEG fixture.
# Output: The destination path after writing a deterministic synthetic image.
# The function writes the fixture at test runtime and uses no external data.
def write_synthetic_jpg(path: Path) -> Path:
    Image.fromarray(_synthetic_rgb_array(), mode="RGB").save(
        path,
        format="JPEG",
        quality=95,
        subsampling=0,
    )
    return path


def write_synthetic_pdf_run(root: Path) -> tuple[Path, Path]:
    """Write a small deterministic preview and matching run annotation."""
    root.mkdir(parents=True, exist_ok=True)
    preview_path = root / "preview.png"
    annotated_path = root / "preview_annotated.png"
    width, height = 320, 180
    pixels = np.zeros((height, width, 3), dtype=np.uint8)
    pixels[:, :, 0] = np.arange(width, dtype=np.uint8)
    pixels[:, :, 1] = np.arange(height, dtype=np.uint8)[:, np.newaxis]
    pixels[:, :, 2] = 160
    Image.fromarray(pixels, mode="RGB").save(preview_path, format="PNG")
    Image.fromarray(pixels, mode="RGB").save(annotated_path, format="PNG")

    def quad(points: list[tuple[int, int]]) -> list[dict[str, int]]:
        return [{"x": x, "y": y} for x, y in points]

    payload = {
        "schema_version": "0.2.0-prototype",
        "record_type": "dicom_injection_run",
        "run_id": "synthetic-pdf-run",
        "seed": 42,
        "rotation_degrees": 0,
        "source_file": "source.dcm",
        "output_file": "injected.dcm",
        "preview_file": preview_path.name,
        "annotated_preview_file": annotated_path.name,
        "document_type": "dicom",
        "example_type": "synthetic",
        "modality": "OT",
        "identity_id": "SYNTH-PDF-0001",
        "span_annotations": [],
        "box_annotations": [
            {
                "label": "PatientName",
                "text": "SYNTHETIC^PATIENT",
                "rendered_text": "SYNTHETIC^PATIENT",
                "region": "top_left",
                "corners": quad([(10, 10), (90, 10), (90, 30), (10, 30)]),
                "label_corners": None,
                "rotation_degrees": 0,
                "frame_index": 0,
                "font_size_pct": 100,
            },
            {
                "label": "PatientID",
                "text": "SYNTH-0001",
                "rendered_text": "SYNTH-0001",
                "region": "bottom_right",
                "corners": quad([(230, 140), (300, 140), (300, 165), (230, 165)]),
                "label_corners": None,
                "rotation_degrees": 0,
                "frame_index": 0,
                "font_size_pct": 100,
            },
            {
                "label": "StudyID",
                "text": "SYNTH-STUDY",
                "rendered_text": "SYNTH-STUDY",
                "region": "rotated",
                "corners": quad([(150, 40), (180, 55), (165, 85), (135, 70)]),
                "label_corners": None,
                "rotation_degrees": 20,
                "frame_index": 0,
                "font_size_pct": 100,
            },
        ],
        "dicom_tag_annotations": [],
        "run_metadata": {
            "rotation_degrees": 0,
            "placement_mode": "corners",
            "pixel_injection_status": "rendered",
            "pixel_renderer": "synthetic",
            "visible_identity_fields": ["patient_name", "patient_id", "study_id"],
            "tag_only_identity_fields": [],
        },
        "render_metadata": {
            "rotation_degrees": 0,
            "placement_mode": "corners",
            "font_size_pct": 100,
            "font_family": "arial",
            "text_background": None,
            "visible_render_plan": [],
            "seed": 42,
            "allowed_rotations_degrees": [0, 20, 90, 180, 270],
            "frame_count": 1,
            "applied_frame_indices": [0],
            "effective_font_family": "arial",
            "effective_font_size_px": 18,
            "background_enabled": False,
            "background_color": None,
            "geometry_source": "synthetic",
            "renderer_types": ["font_text"],
            "handwriting_assets": [],
            "geometry_notes": "synthetic fixture",
            "mask_alpha_threshold": 8,
            "visible_annotations": [],
        },
    }
    ground_truth_path = root / "ground_truth.json"
    ground_truth_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return ground_truth_path, preview_path
