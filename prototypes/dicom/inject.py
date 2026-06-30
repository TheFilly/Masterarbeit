"""Prototype orchestrator: inject a synthetic identity into a DICOM file."""

import argparse
import json
import random
import re
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from injection_pipeline.engine.dicom_tags import inject_tags
from injection_pipeline.identity.generator import generate_identity
from injection_pipeline.loaders.dicom import load_dicom, summarize_dicom
from injection_pipeline.writers.dicom import save_dicom
from PIL import Image
from injection_pipeline.engine.pixel_injection import (
    ALLOWED_ROTATIONS_DEGREES,
    inject_visible_text,
    inject_visible_text_into_image,
)
from view import create_annotated_preview

_DEFAULT_DICOM_DIR = Path("DycomData/Dicom-Files")
_DEFAULT_IMAGE_DIR = Path("DycomData/images")
_DEFAULT_OUTPUT_DIR = Path("prototypes/dicom/output")
_DEFAULT_INPUT_EXTENSIONS: tuple[str, ...] = (".dcm", ".jpg", ".jpeg")

_TAG_META: dict[str, tuple[str, str]] = {
    "PatientName": ("0010,0010", "PN"),
    "PatientID": ("0010,0020", "LO"),
    "PatientBirthDate": ("0010,0030", "DA"),
    "PatientSex": ("0010,0040", "CS"),
    "AccessionNumber": ("0008,0050", "SH"),
}

_IDENTITY_FIELD_MAP: dict[str, str] = {
    "PatientName": "patient_name",
    "PatientID": "patient_id",
    "PatientBirthDate": "patient_birth_date",
    "PatientSex": "patient_sex",
    "AccessionNumber": "accession_number",
}

_VISIBLE_PIXEL_KEYWORDS: tuple[str, ...] = (
    "PatientName",
    "PatientID",
    "AccessionNumber",
)
_TAG_ONLY_KEYWORDS: tuple[str, ...] = ("PatientBirthDate", "PatientSex")
_SCHEMA_VERSION = "0.2.0-prototype"
_FONT_FAMILY_CHOICES: tuple[str, ...] = ("arial", "calibri", "tahoma", "consolas")
_TEXT_BACKGROUND_CHOICES: tuple[str, ...] = ("white",)
_SHOW_LABEL_BOX_CHOICES: tuple[str, ...] = ("y", "n")


# Input: `manifest_path` mit Pfad zum Handschrift-Asset-Manifest.
# Output: Mapping von Asset-ID auf normalisierte Asset-Metadaten.
# Die Funktion loest Bild- und Maskenpfade relativ zum Manifest auf und meldet
# fehlende lokale Artefakte mit sprechenden Fehlern.
def _load_handwriting_manifest(manifest_path: Path) -> dict[str, dict[str, Any]]:
    if not manifest_path.exists():
        raise FileNotFoundError(
            "Handwriting manifest not found: "
            f"{manifest_path}. Generate assets first or pass the actual "
            "manifest.json/jsonl path under DycomData/HandwritingAssets."
        )

    raw_text = manifest_path.read_text(encoding="utf-8")
    if manifest_path.suffix.lower() == ".jsonl":
        raw_assets = [
            json.loads(line)
            for line in raw_text.splitlines()
            if line.strip()
        ]
    else:
        payload = json.loads(raw_text)
        raw_assets = payload.get("assets")
        if not isinstance(raw_assets, list):
            raise ValueError("Handwriting manifest must contain an assets list.")

    manifest_root = manifest_path.parent
    assets: dict[str, dict[str, Any]] = {}
    for raw_asset in raw_assets:
        if not isinstance(raw_asset, dict):
            continue
        asset_id = str(raw_asset.get("asset_id", ""))
        if not asset_id:
            raise ValueError("Handwriting asset is missing asset_id.")
        image_path = manifest_root / str(raw_asset["image_path"])
        mask_path = manifest_root / str(raw_asset["mask_path"])
        if not image_path.exists():
            raise FileNotFoundError(
                f"Handwriting asset {asset_id!r} image not found: {image_path}"
            )
        if not mask_path.exists():
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


# Input: `raw_mappings` mit CLI-Werten im Format `identity_field=asset_id`.
# Output: Mapping von Identity-Feld auf Asset-ID.
# Die Funktion meldet ungueltige CLI-Werte mit ValueError.
def _parse_handwriting_asset_mappings(raw_mappings: list[str]) -> dict[str, str]:
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
def _apply_handwriting_assets(
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
        asset_text = asset.get("text")
        if asset_text != item.get("text"):
            raise ValueError(
                f"Handwriting asset {asset_id!r} text does not match current "
                "render text."
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


# Input: `dicom_dir` und `image_dir` mit Prototype-Quellordnern.
# Output: Sortierte Liste erlaubter Default-Eingabedateien.
# Die Funktion sammelt nur direkt abgelegte DICOM- und JPG/JPEG-Dateien und
# ignoriert andere Formate.
def _collect_default_input_candidates(
    dicom_dir: Path = _DEFAULT_DICOM_DIR,
    image_dir: Path = _DEFAULT_IMAGE_DIR,
) -> list[Path]:
    candidates: list[Path] = []
    for directory in (dicom_dir, image_dir):
        if not directory.exists():
            continue
        candidates.extend(
            path
            for path in directory.iterdir()
            if path.is_file() and path.suffix.lower() in _DEFAULT_INPUT_EXTENSIONS
        )
    return sorted(candidates, key=lambda path: str(path).lower())


# Input: `candidates` mit moeglichen Default-Eingabedateien.
# Output: Zufallig ausgewaehlter Pfad.
# Die Funktion nutzt bewusst nicht-deterministische Auswahl fuer den Prototypen
# und meldet fehlende Kandidaten mit ValueError.
def _select_random_default_input(candidates: list[Path]) -> Path:
    if not candidates:
        raise ValueError(
            "No default input files found in "
            f"{_DEFAULT_DICOM_DIR} or {_DEFAULT_IMAGE_DIR}."
        )
    return random.choice(candidates)


# Input: Keine Parameter.
# Output: Zufaellig ausgewaehlter Default-Eingabepfad.
# TODO: In der spaeteren Pipeline muss diese Auswahl wieder reproduzierbar
# werden; fuer den Prototypen ist nicht-deterministisches Sampling gewollt.
def _select_default_input_path() -> Path:
    return _select_random_default_input(_collect_default_input_candidates())


# Input: `raw_input` mit optionalem CLI-Pfad.
# Output: Eingabepfad und Flag, ob er automatisch gewaehlt wurde.
# Die Funktion priorisiert explizite Nutzereingaben und nutzt nur ohne Pfad den
# zufaelligen Prototype-Default.
def _resolve_input_path(raw_input: str | None) -> tuple[Path, bool]:
    if raw_input:
        return Path(raw_input), False
    return _select_default_input_path(), True


# Input: `input_path` mit Quelleingabepfad.
# Output: Abgeleiteter Beispieltyp als kurzer String.
# Die Funktion nutzt den naechsten aussagekraeftigen Ordnernamen und faellt
# sonst auf `dicom` zurueck.
def _derive_example_type(input_path: Path) -> str:
    for part in reversed(input_path.parts[:-1]):
        normalized = re.sub(r"[^a-z0-9]+", "-", part.lower()).strip("-")
        if normalized and normalized not in {"original-data", "anonymization"}:
            return normalized
    return "dicom"


# Input: `input_path` mit Quelleingabepfad.
# Output: Dokumenttyp `dcm` oder `jpg`.
# Die Funktion prueft die Dateiendung und meldet nicht unterstuetzte Formate
# mit ValueError.
def _detect_input_type(input_path: Path) -> str:
    suffix = input_path.suffix.lower()
    if suffix == ".dcm":
        return "dcm"
    if suffix in {".jpg", ".jpeg"}:
        return "jpg"
    raise ValueError("Unsupported input format. Expected .dcm, .jpg, or .jpeg.")


# Input: Laufparameter wie `filetype`, Zeitstempel, Seed und Renderoptionen.
# Output: Stabiler Run-Identifier fuer Ausgabeordner und Manifest.
# Die Funktion codiert die wichtigsten Reproduzierbarkeitsparameter in einen
# menschenlesbaren Namen.
def _build_run_id(
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


# Input: `output_root`, `run_id`, `source_stem` und `document_type`.
# Output: Pfad-Mapping fuer Ausgabe, Ground Truth, Manifest und Previews.
# Die Funktion erzeugt nur Pfadobjekte; Verzeichnisse werden hier noch nicht
# auf dem Dateisystem angelegt.
def _build_output_paths(
    output_root: Path,
    run_id: str,
    source_stem: str,
    document_type: str,
) -> dict[str, Path]:
    run_dir = output_root / run_id
    output_suffix = ".dcm" if document_type == "dcm" else ".jpg"
    return {
        "run_dir": run_dir,
        "output_file": run_dir / f"{source_stem}_injected{output_suffix}",
        "output_json": run_dir / "ground_truth.json",
        "output_manifest": run_dir / "run_manifest.json",
        "preview_file": run_dir / "preview.png",
        "annotated_preview_file": run_dir / "preview_annotated.png",
    }


# Input: `identity` mit synthetischen Identitaetsfeldern.
# Output: Mapping von DICOM-Keywords auf einzuschreibende Werte.
# Die Funktion uebersetzt das interne Identity-Schema in die prototypeigenen
# DICOM-Tag-Namen.
def _build_tag_map(identity: dict[str, str]) -> dict[str, str]:
    return {
        "PatientName": identity["patient_name"],
        "PatientID": identity["patient_id"],
        "PatientBirthDate": identity["patient_birth_date"],
        "PatientSex": identity["patient_sex"],
        "AccessionNumber": identity["accession_number"],
    }


# Input: `tag_map`, `identity`, `input_path` und `output_path`.
# Output: Liste von Tag-Annotationen fuer den Ground-Truth-Record.
# Die Funktion reichert injizierte Tag-Werte mit DICOM-Adresse, VR und
# Quellen-/Zieldatei an.
def _build_tag_annotations(
    *,
    tag_map: dict[str, str],
    identity: dict[str, str],
    input_path: Path,
    output_path: Path,
) -> list[dict[str, Any]]:
    annotations: list[dict[str, Any]] = []
    for keyword, injected_value in tag_map.items():
        tag_address, dicom_vr = _TAG_META[keyword]
        identity_field = _IDENTITY_FIELD_MAP[keyword]
        annotations.append(
            {
                "label": keyword,
                "tag_address": tag_address,
                "tag_keyword": keyword,
                "dicom_vr": dicom_vr,
                "value": injected_value,
                "identity_field": identity_field,
                "identity_id": identity["patient_id"],
                "source_file": str(input_path),
                "output_file": str(output_path),
            }
        )
    return annotations


# Input: `tag_map` mit sichtbaren Werten, Rotation und Platzierungsmodus.
# Output: Renderplan fuer sichtbare Pixel-Injektionen.
# Die Funktion waehlt die prototypeigen sichtbaren Tags aus und bereitet
# Textsegmente fuer PII- und generische Anteile vor.
def _build_visible_render_plan(
    *,
    tag_map: dict[str, str],
    rotation_degrees: int,
    placement_mode: str,
) -> list[dict[str, Any]]:
    render_plan: list[dict[str, Any]] = []
    for index, keyword in enumerate(_VISIBLE_PIXEL_KEYWORDS):
        render_text, text_segments = _build_text_segments(keyword, tag_map[keyword])
        render_plan.append(
            {
                "label": keyword,
                "text": render_text,
                "text_segments": text_segments,
                "identity_field": _IDENTITY_FIELD_MAP[keyword],
                "region": placement_mode,
                "rotation_degrees": rotation_degrees,
                "line_index": index,
            }
        )
    return render_plan


# Input: `keyword` mit DICOM-Keyword, `value` mit sichtbarem Text.
# Output: Rendertext und segmentierte Textanteile.
# Die Funktion trennt bekannte generische Praefixe von PII-Anteilen und faellt
# sonst auf ein einzelnes PII-Segment zurueck.
def _build_text_segments(keyword: str, value: str) -> tuple[str, list[dict[str, str]]]:
    if keyword == "PatientID" and value.startswith("SYNTH-"):
        return value, [
            {"kind": "generic", "text": "SYNTH-"},
            {"kind": "pii", "text": value.removeprefix("SYNTH-")},
        ]
    if keyword == "AccessionNumber" and value.startswith("ACC-"):
        return value, [
            {"kind": "generic", "text": "ACC-"},
            {"kind": "pii", "text": value.removeprefix("ACC-")},
        ]
    return value, [{"kind": "pii", "text": value}]


# Input: `ds` mit DICOM-Dataset, sichtbarer Renderplan und Ausgabeparameter.
# Output: Mutiertes Dataset und normalisiertes Pixel-Resultat.
# Die Funktion delegiert an den DICOM-Pixelrenderer und vereinheitlicht dessen
# Rueckgabe fuer den Orchestrator.
def _run_pixel_injection(
    *,
    ds: Any,
    visible_injections: list[dict[str, Any]],
    output_path: Path,
    preview_path: Path,
    seed: int,
    rotation_degrees: int,
    example_type: str,
    font_size_pct: int,
    placement_mode: str,
    font_family: str,
    text_background: str | None,
) -> tuple[Any, dict[str, Any]]:
    result = inject_visible_text(
        ds=ds,
        visible_injections=visible_injections,
        output_path=output_path,
        preview_path=preview_path,
        seed=seed,
        rotation_degrees=rotation_degrees,
        example_type=example_type,
        font_size_pct=font_size_pct,
        placement_mode=placement_mode,
        font_family=font_family,
        text_background=text_background,
    )
    return result.get("dataset", ds), {
        "status": result.get("status", "rendered"),
        "renderer_name": "pixel_injection.inject_visible_text",
        "box_annotations": result.get("box_annotations", []),
        "preview_file": result.get("preview_file"),
        "render_metadata": result.get("render_metadata", {}),
    }


# Input: `image` mit Rasterbild, sichtbarer Renderplan und Renderoptionen.
# Output: Gerendertes Bild und normalisiertes Pixel-Resultat.
# Die Funktion nutzt denselben sichtbaren Renderer fuer JPG-Eingaben und
# vereinheitlicht dessen Rueckgabe fuer den Orchestrator.
def _run_jpg_pixel_injection(
    *,
    image: Image.Image,
    visible_injections: list[dict[str, Any]],
    preview_path: Path,
    seed: int,
    rotation_degrees: int,
    example_type: str,
    font_size_pct: int,
    placement_mode: str,
    font_family: str,
    text_background: str | None,
) -> tuple[Image.Image, dict[str, Any]]:
    del example_type
    result = inject_visible_text_into_image(
        image=image,
        visible_injections=visible_injections,
        preview_path=preview_path,
        seed=seed,
        rotation_degrees=rotation_degrees,
        font_size_pct=font_size_pct,
        placement_mode=placement_mode,
        font_family=font_family,
        text_background=text_background,
    )
    return result["image"], {
        "status": result.get("status", "rendered"),
        "renderer_name": "pixel_injection.inject_visible_text_into_image",
        "box_annotations": result.get("box_annotations", []),
        "preview_file": result.get("preview_file"),
        "render_metadata": result.get("render_metadata", {}),
    }


# Input: `value` mit verschachtelten Prototype-Metadaten.
# Output: JSON-taugliche Kopie mit serialisierten Pfaden und Sequenzen.
# Die Funktion bereitet interne Renderdaten fuer Ground-Truth-Artefakte vor,
# ohne die urspruenglichen Objekte fuer den Renderer zu veraendern.
def _make_json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _make_json_safe(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_make_json_safe(item) for item in value]
    return value


# Input: Run-Parameter, Pfade, Identitaet, Annotationen und `pixel_result`.
# Output: Vollstaendiger JSON-tauglicher Ground-Truth-Record.
# Die Funktion buendelt Tag-, Box- und Render-Metadaten in der aktuellen
# Prototype-Schemaversion.
def _build_record(
    *,
    run_id: str,
    seed: int,
    rotation_degrees: int,
    placement_mode: str,
    font_size_pct: int,
    font_family: str,
    text_background: str | None,
    document_type: str,
    example_type: str,
    input_path: Path,
    output_path: Path,
    preview_path: Path,
    annotated_preview_path: Path,
    identity: dict[str, str],
    source_dicom_context: dict[str, Any] | None,
    output_dicom_context: dict[str, Any] | None,
    tag_annotations: list[dict[str, Any]],
    box_annotations: list[dict[str, Any]],
    visible_render_plan: list[dict[str, Any]],
    pixel_result: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": _SCHEMA_VERSION,
        "record_type": f"{document_type}_injection_run",
        "run_id": run_id,
        "seed": seed,
        "rotation_degrees": rotation_degrees,
        "source_file": str(input_path),
        "output_file": str(output_path),
        "preview_file": pixel_result["preview_file"] or str(preview_path),
        "annotated_preview_file": str(annotated_preview_path),
        "document_type": document_type,
        "example_type": example_type,
        "modality": (
            output_dicom_context["modality"]
            if output_dicom_context is not None
            else None
        ),
        "identity_id": identity["patient_id"],
        "span_annotations": [],
        "box_annotations": box_annotations,
        "dicom_tag_annotations": tag_annotations,
        "run_metadata": {
            "rotation_degrees": rotation_degrees,
            "placement_mode": placement_mode,
            "pixel_injection_status": pixel_result["status"],
            "pixel_renderer": pixel_result["renderer_name"],
            "visible_identity_fields": [
                _IDENTITY_FIELD_MAP[keyword] for keyword in _VISIBLE_PIXEL_KEYWORDS
            ],
            "tag_only_identity_fields": [
                _IDENTITY_FIELD_MAP[keyword] for keyword in _TAG_ONLY_KEYWORDS
            ],
        },
        "render_metadata": {
            "rotation_degrees": rotation_degrees,
            "placement_mode": placement_mode,
            "font_size_pct": font_size_pct,
            "font_family": font_family,
            "text_background": text_background,
            "visible_render_plan": _make_json_safe(visible_render_plan),
            **_make_json_safe(pixel_result["render_metadata"]),
        },
    }


# Input: `record` mit Run-Metadaten und optionale DICOM-Kontexte.
# Output: Dasselbe Record-Objekt mit angehaengten Kontexten.
# Die Funktion mutiert den Record nur, wenn Quell- und Ausgabekontext vorhanden
# sind, damit JPG-Laeufe keine leeren DICOM-Felder erhalten.
def _attach_dicom_contexts(
    record: dict[str, Any],
    *,
    source_dicom_context: dict[str, Any] | None,
    output_dicom_context: dict[str, Any] | None,
) -> dict[str, Any]:
    if source_dicom_context is not None and output_dicom_context is not None:
        record["run_metadata"]["source_dicom_context"] = source_dicom_context
        record["run_metadata"]["output_dicom_context"] = output_dicom_context
    return record


# Input: `raw_value` mit Nutzereingabe, `parameter_name` fuer Fehlermeldungen.
# Output: Geparster Integer.
# Die Funktion kapselt die CLI-Fehlermeldung und wirft bei ungueltigen Werten
# einen ValueError mit Parameterbezug.
def _parse_int(raw_value: str, parameter_name: str) -> int:
    try:
        return int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{parameter_name} must be a whole number.") from exc


# Input: `rotation_angle` mit angefordertem Winkel.
# Output: Validierter Winkel.
# Die Funktion akzeptiert nur die prototypeigenen Rotationen und meldet andere
# Werte mit ValueError.
def _validate_rotation_angle(rotation_angle: int) -> int:
    if rotation_angle not in ALLOWED_ROTATIONS_DEGREES:
        allowed = ", ".join(str(angle) for angle in ALLOWED_ROTATIONS_DEGREES)
        raise ValueError(f"rotation-angle must be one of [{allowed}].")
    return rotation_angle


# Input: `font_size_pct` mit relativer Schriftgroesse.
# Output: Validierter Prozentwert.
# Die Funktion verhindert nichtpositive Schriftgroessen und gibt gueltige Werte
# unveraendert zurueck.
def _validate_font_size_pct(font_size_pct: int) -> int:
    if font_size_pct < 1:
        raise ValueError("font-size-pct must be >= 1.")
    return font_size_pct


# Input: `parameter_name`, `value` und erlaubte `choices`.
# Output: Validierter Auswahlwert.
# Die Funktion prueft interaktive und CLI-nahe Auswahlwerte und erzeugt eine
# knappe ValueError-Meldung mit allen erlaubten Optionen.
def _validate_choice(parameter_name: str, value: str, choices: tuple[str, ...]) -> str:
    if value not in choices:
        allowed = ", ".join(choices)
        raise ValueError(f"{parameter_name} must be one of: {allowed}.")
    return value


# Input: Prompt-Metadaten, optionaler Default und `parser` fuer die Eingabe.
# Output: Geparster interaktiver Wert.
# Die Funktion wiederholt die Eingabe bis ein valider Wert vorliegt und schreibt
# Validierungsfehler auf stdout.
def _prompt_for_value(
    *,
    parameter_name: str,
    purpose: str,
    expected_inputs: str,
    default_value: str | int | None,
    parser: Callable[[str], Any],
) -> Any:
    default_suffix = "" if default_value is None else f" Default: {default_value}."
    prompt = (
        f"{parameter_name}: {purpose} Expected input: "
        f"{expected_inputs}.{default_suffix}\n> "
    )
    while True:
        raw_value = input(prompt).strip()
        if raw_value == "" and default_value is not None:
            return default_value
        if raw_value == "":
            print("Please enter a value.")
            continue
        try:
            return parser(raw_value)
        except ValueError as exc:
            print(f"Invalid {parameter_name}: {exc}")


# Input: `default_value` mit voreingestelltem Hintergrundmodus.
# Output: `white` oder `None`.
# Die Funktion fragt interaktiv nach einem weissen Texthintergrund und wiederholt
# die Eingabe bei ungueltigen Antworten.
def _prompt_for_text_background(default_value: str | None) -> str | None:
    default_label = "n" if default_value is None else "y"
    prompt = (
        "text-background: Choose whether visible injected text should get a white "
        "background box for readability. Expected input: y or n. "
        f"Default: {default_label} ({default_value}).\n> "
    )
    while True:
        raw_value = input(prompt).strip().lower()
        if raw_value == "":
            return default_value
        if raw_value == "y":
            return "white"
        if raw_value == "n":
            return None
        print("Invalid text-background: enter 'y' for white or 'n' for no background.")


# Input: `default_value` mit voreingestellter Ja/Nein-Auswahl.
# Output: `y` oder `n`.
# Die Funktion fragt interaktiv, ob generische Label-Boxen angezeigt werden, und
# akzeptiert nur die prototypeigenen Auswahlwerte.
def _prompt_for_show_label_boxes(default_value: str) -> str:
    prompt = (
        "show-label-boxes: Choose whether generic label prefixes such as "
        "SYNTH- or ACC- "
        "should be outlined in preview_annotated.png. Expected input: y or n. "
        f"Default: {default_value}.\n> "
    )
    while True:
        raw_value = input(prompt).strip().lower()
        if raw_value == "":
            return default_value
        if raw_value in _SHOW_LABEL_BOX_CHOICES:
            return raw_value
        print("Invalid show-label-boxes: enter 'y' or 'n'.")


# Input: Keine Parameter.
# Output: Expliziter Eingabepfad als String oder `None` fuer Zufallsauswahl.
# Die Funktion fragt im interaktiven Modus zuerst nach Zufallsauswahl und
# validiert bei manueller Auswahl, dass der angegebene Pfad existiert.
def _prompt_for_input_path() -> str | None:
    prompt = (
        "input: Use a random local DICOM/JPG input file? Expected input: y or n. "
        "Default: y.\n> "
    )
    while True:
        raw_value = input(prompt).strip().lower()
        if raw_value in ("", "y"):
            return None
        if raw_value == "n":
            while True:
                raw_path = input(
                    "input-path: Enter path to a .dcm, .jpg, or .jpeg file.\n> "
                ).strip()
                if raw_path == "":
                    print("Invalid input-path: please enter a path.")
                    continue
                input_path = Path(raw_path)
                if not input_path.exists():
                    print(f"Invalid input-path: file not found: {input_path}")
                    continue
                if input_path.suffix.lower() not in _DEFAULT_INPUT_EXTENSIONS:
                    print(
                        "Invalid input-path: expected one of "
                        f"{', '.join(_DEFAULT_INPUT_EXTENSIONS)}."
                    )
                    continue
                return raw_path
        print("Invalid input: enter 'y' for random input or 'n' to provide a path.")


# Input: Keine Parameter.
# Output: argparse-Namespace mit interaktiv gesammelten Laufparametern.
# Die Funktion fuehrt den parametergefuehrten Prompt-Modus aus und validiert
# Einzelwerte direkt waehrend der Eingabe.
def _collect_interactive_args() -> argparse.Namespace:
    print("No CLI arguments were provided. Starting interactive parameter setup.\n")
    input_path = _prompt_for_input_path()
    seed = _prompt_for_value(
        parameter_name="seed",
        purpose=(
            "Seed for reproducible synthetic identity generation and placement "
            "randomness."
        ),
        expected_inputs="an integer",
        default_value=42,
        parser=lambda raw: _parse_int(raw, "seed"),
    )
    rotation_angle = _prompt_for_value(
        parameter_name="rotation-angle",
        purpose="Rotation angle in degrees for visible injected text.",
        expected_inputs=(
            "one of " + ", ".join(str(angle) for angle in ALLOWED_ROTATIONS_DEGREES)
        ),
        default_value=0,
        parser=lambda raw: _validate_rotation_angle(_parse_int(raw, "rotation-angle")),
    )
    font_size_pct = _prompt_for_value(
        parameter_name="font-size-pct",
        purpose=(
            "Font size for visible injected text as a percentage of the "
            "prototype default."
        ),
        expected_inputs="an integer >= 1",
        default_value=100,
        parser=lambda raw: _validate_font_size_pct(_parse_int(raw, "font-size-pct")),
    )
    placement_mode = _prompt_for_value(
        parameter_name="placement-mode",
        purpose="Placement strategy for visible injected text.",
        expected_inputs="free or corners",
        default_value="corners",
        parser=lambda raw: _validate_choice(
            "placement-mode", raw, ("free", "corners")
        ),
    )
    font_family = _prompt_for_value(
        parameter_name="font-family",
        purpose="Prototype font family used for visible injected text rendering.",
        expected_inputs=f"one of {', '.join(_FONT_FAMILY_CHOICES)}",
        default_value="arial",
        parser=lambda raw: _validate_choice("font-family", raw, _FONT_FAMILY_CHOICES),
    )
    text_background = _prompt_for_text_background(default_value=None)
    show_label_boxes = _prompt_for_show_label_boxes(default_value="n")
    return argparse.Namespace(
        seed=seed,
        input=input_path,
        output_dir=str(_DEFAULT_OUTPUT_DIR),
        handwriting_manifest=None,
        handwriting_asset=[],
        rotation_angle=rotation_angle,
        font_size_pct=font_size_pct,
        placement_mode=placement_mode,
        font_family=font_family,
        text_background=text_background,
        show_label_boxes=show_label_boxes,
    )


# Input: `args` mit geparsten CLI- oder interaktiven Parametern.
# Output: Keine Rueckgabe.
# Die Funktion validiert die globalen Grenzwerte vor dem Lauf und wirft bei
# ungueltigen Optionen ValueError.
def _validate_args(args: argparse.Namespace) -> None:
    if args.rotation_angle not in ALLOWED_ROTATIONS_DEGREES:
        allowed = ", ".join(str(angle) for angle in ALLOWED_ROTATIONS_DEGREES)
        raise ValueError(
            f"--rotation-angle must be one of [{allowed}], got {args.rotation_angle}."
        )
    if args.font_size_pct < 1:
        raise ValueError("--font-size-pct must be >= 1.")
    if args.handwriting_asset and args.handwriting_manifest is None:
        raise ValueError("--handwriting-asset requires --handwriting-manifest.")


# Entry point for the DICOM injection prototype.
def main() -> None:
    parser = argparse.ArgumentParser(description="DICOM injection prototype")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--input", type=str, default=None)
    parser.add_argument("--output-dir", type=str, default=str(_DEFAULT_OUTPUT_DIR))
    parser.add_argument("--rotation-angle", type=int, default=0)
    parser.add_argument(
        "--font-size-pct",
        type=int,
        default=100,
        metavar="PERCENT",
        help=(
            "Font size as a percentage of the default size "
            "(100 = default, 50 = half size). Must be >= 1."
        ),
    )
    parser.add_argument(
        "--placement-mode",
        type=str,
        default="corners",
        choices=["free", "corners"],
        help=(
            "Placement mode: 'corners' picks a random corner, "
            "'free' picks a fully random position."
        ),
    )
    parser.add_argument(
        "--font-family",
        type=str,
        default="arial",
        choices=list(_FONT_FAMILY_CHOICES),
        help=(
            "Prototype font family choice. Only fixed Windows-style choices "
            "are supported."
        ),
    )
    parser.add_argument(
        "--text-background",
        type=str,
        default=None,
        choices=list(_TEXT_BACKGROUND_CHOICES),
        help="Optional visible text background. Currently only 'white' is supported.",
    )
    parser.add_argument(
        "--show-label-boxes",
        type=str,
        default="n",
        choices=list(_SHOW_LABEL_BOX_CHOICES),
        help=(
            "Show generic label-prefix boxes such as SYNTH- or ACC- in "
            "preview_annotated.png."
        ),
    )
    parser.add_argument(
        "--handwriting-manifest",
        type=str,
        default=None,
        help="Optional handwriting asset manifest for manifest-controlled overlays.",
    )
    parser.add_argument(
        "--handwriting-asset",
        action="append",
        default=[],
        metavar="FIELD=ASSET_ID",
        help="Map an identity field such as patient_name to a handwriting asset ID.",
    )
    args = _collect_interactive_args() if len(sys.argv) == 1 else parser.parse_args()
    _validate_args(args)

    input_path, was_auto_selected = _resolve_input_path(args.input)
    if was_auto_selected:
        print(f"Auto-selected input: {input_path}")
    output_root = Path(args.output_dir)
    document_type = _detect_input_type(input_path)
    example_type = _derive_example_type(input_path)
    run_id = _build_run_id(
        filetype=document_type,
        run_timestamp=datetime.now(),
        seed=args.seed,
        rotation_degrees=args.rotation_angle,
        placement_mode=args.placement_mode,
        font_size_pct=args.font_size_pct,
        font_family=args.font_family,
        text_background=args.text_background,
    )
    output_paths = _build_output_paths(
        output_root,
        run_id,
        input_path.stem,
        document_type,
    )

    identity_a = generate_identity(args.seed)
    identity_b = generate_identity(args.seed + 1)

    tag_map = _build_tag_map(identity_a)
    visible_render_plan = _build_visible_render_plan(
        tag_map=tag_map,
        rotation_degrees=args.rotation_angle,
        placement_mode=args.placement_mode,
    )
    if args.handwriting_manifest is not None:
        handwriting_manifest = _load_handwriting_manifest(
            Path(args.handwriting_manifest)
        )
        visible_render_plan = _apply_handwriting_assets(
            visible_render_plan,
            handwriting_manifest,
            _parse_handwriting_asset_mappings(args.handwriting_asset),
        )
    output_paths["run_dir"].mkdir(parents=True, exist_ok=True)
    source_dicom_context: dict[str, Any] | None = None
    output_dicom_context: dict[str, Any] | None = None

    # DICOM keeps the tag-injection path; JPG reuses only the visible-rendering path.
    if document_type == "dcm":
        ds = load_dicom(input_path)
        source_dicom_context = summarize_dicom(ds)
        ds = inject_tags(ds, tag_map)
        ds, pixel_result = _run_pixel_injection(
            ds=ds,
            visible_injections=visible_render_plan,
            output_path=output_paths["output_file"],
            preview_path=output_paths["preview_file"],
            seed=args.seed,
            rotation_degrees=args.rotation_angle,
            example_type=example_type,
            font_size_pct=args.font_size_pct,
            placement_mode=args.placement_mode,
            font_family=args.font_family,
            text_background=args.text_background,
        )
        output_dicom_context = summarize_dicom(ds)
        save_dicom(ds, output_paths["output_file"])
        tag_annotations = _build_tag_annotations(
            tag_map=tag_map,
            identity=identity_a,
            input_path=input_path,
            output_path=output_paths["output_file"],
        )
    else:
        image = Image.open(input_path).convert("RGB")
        image, pixel_result = _run_jpg_pixel_injection(
            image=image,
            visible_injections=visible_render_plan,
            preview_path=output_paths["preview_file"],
            seed=args.seed,
            rotation_degrees=args.rotation_angle,
            example_type=example_type,
            font_size_pct=args.font_size_pct,
            placement_mode=args.placement_mode,
            font_family=args.font_family,
            text_background=args.text_background,
        )
        image.save(output_paths["output_file"], format="JPEG")
        tag_annotations = []

    create_annotated_preview(
        source_path=pixel_result["preview_file"] or output_paths["preview_file"],
        box_annotations=pixel_result["box_annotations"],
        output_path=output_paths["annotated_preview_file"],
        title=input_path.stem,
        show_label_boxes=args.show_label_boxes == "y",
    )

    record = _attach_dicom_contexts(
        _build_record(
        run_id=run_id,
        seed=args.seed,
        rotation_degrees=args.rotation_angle,
        placement_mode=args.placement_mode,
        font_size_pct=args.font_size_pct,
        font_family=args.font_family,
        text_background=args.text_background,
        document_type=document_type,
        example_type=example_type,
        input_path=input_path,
        output_path=output_paths["output_file"],
        preview_path=output_paths["preview_file"],
        annotated_preview_path=output_paths["annotated_preview_file"],
        identity=identity_a,
        source_dicom_context=source_dicom_context,
        output_dicom_context=output_dicom_context,
        tag_annotations=tag_annotations,
        box_annotations=pixel_result["box_annotations"],
        visible_render_plan=visible_render_plan,
        pixel_result=pixel_result,
        ),
        source_dicom_context=source_dicom_context,
        output_dicom_context=output_dicom_context,
    )

    with output_paths["output_json"].open("w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2)
        fh.write("\n")

    with output_paths["output_manifest"].open("w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2)

    print(
        f"Run {run_id} written to {output_paths['run_dir']}\n"
        f"Injected {len(tag_annotations)} tags into {output_paths['output_file']}\n"
        f"Ground truth written to {output_paths['output_json']}\n"
        f"Preview:            {output_paths['preview_file']}\n"
        f"Annotated preview:  {output_paths['annotated_preview_file']}"
    )
    print(f"Pixel injection status: {pixel_result['status']}")

    print("\nSecond identity (seed+1, not injected):")
    for key, value in identity_b.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
