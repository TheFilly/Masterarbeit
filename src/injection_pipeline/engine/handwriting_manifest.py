"""Handwriting asset manifest loading and render-plan attachment."""

import json
from pathlib import Path
from typing import Any


# Input: `manifest_path` mit Pfad zum Handschrift-Asset-Manifest.
# Output: Mapping von Asset-ID auf normalisierte Asset-Metadaten.
# Die Funktion loest Bild- und Maskenpfade relativ zum Manifest auf und meldet
# fehlende lokale Artefakte mit sprechenden Fehlern.
def load_handwriting_manifest(manifest_path: Path) -> dict[str, dict[str, Any]]:
    if not manifest_path.exists():
        raise FileNotFoundError(
            "Handwriting manifest not found: "
            f"{manifest_path}. Generate assets first or pass the actual "
            "manifest.json/jsonl path under DicomData/HandwritingAssets."
        )

    raw_text = manifest_path.read_text(encoding="utf-8")
    if manifest_path.suffix.lower() == ".jsonl":
        raw_assets = [
            json.loads(line) for line in raw_text.splitlines() if line.strip()
        ]
    else:
        payload = json.loads(raw_text)
        raw_assets = payload.get("assets")
        if not isinstance(raw_assets, list):
            raise ValueError("Handwriting manifest must contain an assets list.")

    manifest_root = manifest_path.parent.resolve()
    assets: dict[str, dict[str, Any]] = {}
    for raw_asset in raw_assets:
        if not isinstance(raw_asset, dict):
            raise ValueError("Handwriting manifest assets must be objects.")
        raw_asset_id = raw_asset.get("asset_id")
        if not isinstance(raw_asset_id, str) or not raw_asset_id:
            raise ValueError("Handwriting asset is missing asset_id.")
        asset_id = raw_asset_id
        if asset_id in assets:
            raise ValueError(f"Duplicate handwriting asset ID: {asset_id!r}.")
        image_path = _resolve_manifest_asset_path(
            manifest_root, raw_asset.get("image_path"), asset_id, "image"
        )
        mask_path = _resolve_manifest_asset_path(
            manifest_root, raw_asset.get("mask_path"), asset_id, "mask"
        )
        if not image_path.is_file():
            raise FileNotFoundError(
                f"Handwriting asset {asset_id!r} image not found: {image_path}"
            )
        if not mask_path.is_file():
            raise FileNotFoundError(
                f"Handwriting asset {asset_id!r} mask not found: {mask_path}"
            )
        assets[asset_id] = {
            **raw_asset,
            "asset_id": asset_id,
            "identity_field": raw_asset.get("identity_field", raw_asset.get("field")),
            "background_mode": raw_asset.get(
                "background_mode", raw_asset.get("background")
            ),
            "image_path": image_path,
            "mask_path": mask_path,
        }
    return assets


# Input: Manifestwurzel, relativer Assetpfad, Asset-ID und Assettyp.
# Output: Aufgeloester Pfad innerhalb der Manifestwurzel.
# Die Funktion lehnt absolute Pfade und Parent-Traversal einschliesslich
# Symlink-Ausbruechen ab, bevor externe Bild- oder Maskendateien gelesen werden.
def _resolve_manifest_asset_path(
    manifest_root: Path,
    raw_path: object,
    asset_id: str,
    asset_kind: str,
) -> Path:
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise ValueError(
            f"Handwriting asset {asset_id!r} is missing a {asset_kind} path."
        )
    candidate = Path(raw_path)
    if candidate.is_absolute():
        raise ValueError(
            f"Handwriting asset {asset_id!r} {asset_kind} path must be relative."
        )
    resolved = (manifest_root / candidate).resolve()
    try:
        resolved.relative_to(manifest_root)
    except ValueError as exc:
        raise ValueError(
            f"Handwriting asset {asset_id!r} {asset_kind} path escapes manifest."
        ) from exc
    return resolved


# Input: `raw_mappings` mit CLI-Werten im Format `identity_field=asset_id`.
# Output: Mapping von Identity-Feld auf Asset-ID.
# Die Funktion meldet ungueltige CLI-Werte mit ValueError.
def parse_handwriting_asset_mappings(raw_mappings: list[str]) -> dict[str, str]:
    mappings: dict[str, str] = {}
    for raw_mapping in raw_mappings:
        if "=" not in raw_mapping:
            raise ValueError(
                "--handwriting-asset must use identity_field=asset_id syntax."
            )
        identity_field, asset_id = raw_mapping.split("=", 1)
        identity_field = identity_field.strip()
        asset_id = asset_id.strip()
        if not identity_field or not asset_id:
            raise ValueError(
                "--handwriting-asset requires non-empty field and asset ID."
            )
        mappings[identity_field] = asset_id
    return mappings


# Input: `render_plan`, Asset-Manifest und Feld-zu-Asset-Zuordnung.
# Output: Renderplan mit angehaengten Handschrift-Assets.
# Die Funktion laesst nicht zugeordnete Felder im normalen Text-Renderer.
def apply_handwriting_assets(
    render_plan: list[dict[str, Any]],
    manifest: dict[str, dict[str, Any]],
    asset_mappings: dict[str, str],
) -> list[dict[str, Any]]:
    updated_plan: list[dict[str, Any]] = []
    for item in render_plan:
        identity_field = str(item.get("identity_field", ""))
        asset_id = asset_mappings.get(identity_field)
        if asset_id is None:
            updated_plan.append(item)
            continue
        if asset_id not in manifest:
            raise ValueError(f"Unknown handwriting asset ID: {asset_id}")
        asset = manifest[asset_id]
        asset_identity_field = asset.get("identity_field")
        if asset_identity_field != identity_field:
            raise ValueError(
                f"Handwriting asset {asset_id!r} has identity field "
                f"{asset_identity_field!r}, expected {identity_field!r}."
            )
        asset_text = asset.get("source_text", asset.get("text"))
        if asset_text != item.get("text"):
            raise ValueError(
                f"Handwriting asset {asset_id!r} source text does not match "
                "current render text."
            )
        updated_plan.append(
            {
                **item,
                "renderer_type": "handwriting_asset",
                "asset_id": asset_id,
                "asset": asset,
            }
        )
    return updated_plan
