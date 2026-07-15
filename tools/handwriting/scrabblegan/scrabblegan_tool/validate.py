"""Validation for generated ScrabbleGAN handwriting asset manifests."""

import os
from pathlib import Path

from PIL import Image

from .hashing import require_sha256, sha256_file
from .manifest import (
    ALLOWED_BACKGROUNDS,
    ALLOWED_FIELDS,
    ALLOWED_INK_COLORS,
    load_output_manifest,
)


# Input: Checkpoint-Pfad und erwarteter SHA-256.
# Output: Keine Rueckgabe.
# Die Funktion prueft Existenz und Hash des lokal bereitgestellten Modells vor
# einem Render- oder Validierungslauf.
def validate_checkpoint(checkpoint_path, checkpoint_sha256):
    # type: (Path, str) -> None
    require_sha256(checkpoint_path, checkpoint_sha256)


# Input: `manifest_path`, Checkpoint-Pfad und erwarteter Checkpoint-Hash.
# Output: Liste validierter Output-Records.
# Die Funktion prueft Manifest, relative Pfade, Bild-/Maskenartefakte, Hashes,
# BBoxen und erlaubte v1-Optionen.
def validate_output_manifest(manifest_path, checkpoint_path, checkpoint_sha256):
    # type: (Path, Path, str) -> list
    validate_checkpoint(checkpoint_path, checkpoint_sha256)
    records = load_output_manifest(manifest_path)
    manifest_root = manifest_path.parent
    seen_asset_ids = set()

    for index, record in enumerate(records, start=1):
        _validate_record_shape(record, index)
        asset_id = record["asset_id"]
        if asset_id in seen_asset_ids:
            raise ValueError(f"Duplicate asset_id in output manifest: {asset_id}")
        seen_asset_ids.add(asset_id)

        if record["checkpoint_sha256"] != checkpoint_sha256:
            raise ValueError(f"checkpoint_sha256 mismatch for asset {asset_id}")

        image_path = _resolve_relative_asset_path(
            manifest_root, record["image_path"], "image_path", asset_id
        )
        mask_path = _resolve_relative_asset_path(
            manifest_root, record["mask_path"], "mask_path", asset_id
        )
        if sha256_file(image_path) != record["image_sha256"]:
            raise ValueError(f"image_sha256 mismatch for asset {asset_id}")
        if sha256_file(mask_path) != record["mask_sha256"]:
            raise ValueError(f"mask_sha256 mismatch for asset {asset_id}")

        _validate_images(image_path, mask_path, record)
    return records


# Input: Einzelner Output-Record und `index` fuer Fehlertexte.
# Output: Keine Rueckgabe.
# Die Funktion prueft Pflichtfelder und erlaubte v1-Werte.
def _validate_record_shape(record, index):
    # type: (dict, int) -> None
    required = (
        "asset_id",
        "field",
        "text",
        "image_path",
        "mask_path",
        "image_sha256",
        "mask_sha256",
        "checkpoint_sha256",
        "scrabblegan_repo_url",
        "scrabblegan_commit",
        "ink_color",
        "background",
        "seed",
        "ink_bbox",
        "image_size",
    )
    for key in required:
        if key not in record:
            raise ValueError(f"Output record {index} missing key: {key}")
    if record["field"] not in ALLOWED_FIELDS:
        raise ValueError("Unsupported field in output manifest: {}".format(
            record["field"]
        ))
    if not record["text"]:
        raise ValueError(f"Output record {index} has empty text.")
    if record["ink_color"] not in ALLOWED_INK_COLORS:
        raise ValueError("Unsupported ink_color in output manifest: {}".format(
            record["ink_color"]
        ))
    if record["background"] not in ALLOWED_BACKGROUNDS:
        raise ValueError("Unsupported background in output manifest: {}".format(
            record["background"]
        ))
    if record["ink_color"] == "white" and record["background"] == "white":
        raise ValueError("Invisible white-on-white asset in output manifest: {}".format(
            record["asset_id"]
        ))


# Input: Manifest-Wurzel, relativer Pfad und Feldname.
# Output: Absoluter Pfad innerhalb des Manifestordners.
# Die Funktion verhindert absolute Pfade und Parent-Traversal im konsumierbaren
# Generator-Manifest.
def _resolve_relative_asset_path(manifest_root, raw_path, field_name, asset_id):
    # type: (Path, str, str, str) -> Path
    path = Path(raw_path)
    if path.is_absolute():
        raise ValueError(f"{field_name} for asset {asset_id} must be relative.")
    normalized = os.path.normpath(str(path))
    if normalized.startswith(".."):
        raise ValueError(
            f"{field_name} for asset {asset_id} leaves manifest directory."
        )
    resolved = manifest_root / normalized
    if not resolved.exists():
        raise ValueError(f"{field_name} for asset {asset_id} not found: {resolved}")
    return resolved


# Input: Bildpfad, Maskenpfad und Output-Record.
# Output: Keine Rueckgabe.
# Die Funktion prueft Modus, Groesse, nicht-leere Maske und BBox-Konsistenz.
def _validate_images(image_path, mask_path, record):
    # type: (Path, Path, dict) -> None
    image = Image.open(image_path).convert("RGBA")
    mask = Image.open(mask_path).convert("L")
    if image.size != mask.size:
        raise ValueError("Image and mask size mismatch for asset {}".format(
            record["asset_id"]
        ))
    if mask.getbbox() is None:
        raise ValueError("Mask is empty for asset {}".format(record["asset_id"]))

    expected_size = record["image_size"]
    actual_size = {"width": image.size[0], "height": image.size[1]}
    if expected_size != actual_size:
        raise ValueError("image_size mismatch for asset {}".format(
            record["asset_id"]
        ))

    bbox = mask.getbbox()
    expected_bbox = {
        "x": bbox[0],
        "y": bbox[1],
        "width": bbox[2] - bbox[0],
        "height": bbox[3] - bbox[1],
    }
    if record["ink_bbox"] != expected_bbox:
        raise ValueError("ink_bbox mismatch for asset {}".format(record["asset_id"]))
