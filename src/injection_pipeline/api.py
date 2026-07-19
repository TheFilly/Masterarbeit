"""Public API helpers for single synthetic PII injections."""

import random
import re
import shutil
from argparse import Namespace
from datetime import datetime
from os import PathLike
from pathlib import Path

from injection_pipeline.config.identifier_schema import (
    DEFAULT_IDENTIFIER_SCHEMA_PATH,
    DicomTagRoute,
    FieldSpec,
    GenerationSpec,
    IdentifierSchema,
    RoutingSpec,
    VisiblePixelRoute,
    load_identifier_schema,
)
from injection_pipeline.engine.pixel_injection import ALLOWED_ROTATIONS_DEGREES
from injection_pipeline.models.identity import Identity
from injection_pipeline.runtime.inputs import DEFAULT_DICOM_DIR, DEFAULT_IMAGE_DIR
from injection_pipeline.runtime.options import (
    DEFAULT_HANDWRITING_ASSET_ROOT,
    DEFAULT_HANDWRITING_CHECKPOINT_PATH,
    DEFAULT_HANDWRITING_CONTAINER_IMAGE,
    DEFAULT_HANDWRITING_SOURCE_DIR,
    DEFAULT_OUTPUT_DIR,
    HANDWRITING_FONT_FAMILY,
)
from injection_pipeline.runtime.runner import run as run_pipeline

_DOCUMENT_TYPE_EXTENSIONS: dict[str, tuple[str, ...]] = {
    "dcm": (".dcm",),
    "jpg": (".jpg", ".jpeg"),
}
_DOCUMENT_TYPE_INPUT_DIRS: dict[str, Path] = {
    "dcm": DEFAULT_DICOM_DIR,
    "jpg": DEFAULT_IMAGE_DIR,
}


# Input: `category`, `value`, `prefix`, `suffix`, `handwritten` und `documentType`.
# Output: Validierte Strings, Boolean und normalisierter Dokumenttyp.
# Die Funktion bildet den Fehlerrand der Public API und meldet ungueltige
# Nutzereingaben als ValueError, bevor Dateien gelesen oder geschrieben werden.
def _validate_api_inputs(
    category: str,
    value: str,
    prefix: str,
    suffix: str,
    handwritten: bool,
    documentType: str,
) -> tuple[str, str, str, str, bool, str]:
    if not isinstance(category, str) or category.strip() == "":
        raise ValueError("category must be a non-empty string.")
    if not isinstance(value, str) or value == "":
        raise ValueError("value must be a non-empty string.")
    if not isinstance(prefix, str):
        raise ValueError("prefix must be a string.")
    if not isinstance(suffix, str):
        raise ValueError("suffix must be a string.")
    if not isinstance(handwritten, bool):
        raise ValueError("handwritten must be a boolean.")
    if not isinstance(documentType, str):
        raise ValueError("documentType must be a string.")

    normalized_document_type = documentType.casefold()
    if normalized_document_type not in _DOCUMENT_TYPE_EXTENSIONS:
        raise ValueError("documentType must be one of: dcm, jpg.")
    return category, value, prefix, suffix, handwritten, normalized_document_type


# Input: `document_type` als normalisierter API-Dokumenttyp.
# Output: Zufaellig ausgewaehlter lokaler Quellpfad.
# Die Funktion liest nur die etablierte Default-Quelle des jeweiligen Formats
# und erzeugt keine reproduzierbare Auswahl.
def _select_random_source(document_type: str) -> Path:
    input_dir = _DOCUMENT_TYPE_INPUT_DIRS[document_type]
    allowed_extensions = _DOCUMENT_TYPE_EXTENSIONS[document_type]
    if not input_dir.exists():
        raise ValueError(
            f"No default input directory found for {document_type}: {input_dir}"
        )
    candidates = sorted(
        path
        for path in input_dir.iterdir()
        if path.is_file() and path.suffix.casefold() in allowed_extensions
    )
    if not candidates:
        raise ValueError(
            f"No default {document_type} input files found in {input_dir}."
        )
    return random.SystemRandom().choice(candidates)


# Input: `category` aus der API.
# Output: Normalisierter interner Feldname.
# Die Funktion haelt freie Kategorien schema-kompatibel und vermeidet leere
# Feldnamen, wenn die Kategorie nur aus Sonderzeichen besteht.
def _field_name_from_category(category: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", category.casefold()).strip("_")
    return normalized or "api_field"


# Input: `category` und Default-Identifier-Schema.
# Output: Passendes Schemafeld oder `None`.
# Die Funktion sucht case-insensitiv nur ueber eindeutige Feldnamen und DICOM-
# Keywords. Freie Kategorie-Labels routen dadurch nicht versehentlich native Tags.
def _match_default_schema_field(
    category: str,
    default_schema: IdentifierSchema,
) -> FieldSpec | None:
    normalized_category = category.casefold()
    matches: list[FieldSpec] = []
    for field in default_schema.fields:
        candidates = {field.name.casefold()}
        dicom_tag = field.routing.dicom_tag
        if dicom_tag is not None:
            candidates.add(dicom_tag.keyword.casefold())
        if normalized_category in candidates:
            matches.append(field)
    if len(matches) > 1:
        raise ValueError(f"category {category!r} matches multiple DICOM schema fields.")
    return matches[0] if matches else None


# Input: `category`, `handwritten` und optionales Default-Schemafeld.
# Output: Internes Identity-Feld und optionale DICOM-Tag-Route.
# Die Funktion trennt freie API-Kategorien von nativen DICOM-Routen; Handschrift
# darf beliebige Feldnamen verwenden, weil der API-Pfad Text-Assets direkt anfragt.
def _resolve_api_field(
    *,
    category: str,
    default_schema: IdentifierSchema,
) -> tuple[str, DicomTagRoute | None]:
    matched_field = _match_default_schema_field(category, default_schema)
    dicom_tag = None if matched_field is None else matched_field.routing.dicom_tag
    if matched_field is not None:
        return matched_field.name, dicom_tag
    return _field_name_from_category(category), None


# Input: `field_name`, API-`category` und optionale DICOM-Route.
# Output: In-Memory-Identifier-Schema fuer genau eine sichtbare Injektion.
# Die Funktion verwendet ein minimales Schema, weil die API feste Werte liefert
# und keine Faker-Recipe-Auswertung benoetigt.
def _build_api_schema(
    *,
    field_name: str,
    category: str,
    dicom_tag: DicomTagRoute | None,
    default_schema: IdentifierSchema,
) -> IdentifierSchema:
    return IdentifierSchema(
        schema_id="api-single-injection",
        version="1.0.0",
        description="Single-value schema generated by inject_function().",
        identity_id_field=field_name,
        generator=default_schema.generator,
        fields=[
            FieldSpec(
                name=field_name,
                category=category,
                generation=GenerationSpec(
                    recipe="random_element",
                    arguments={"elements": ["unused"]},
                    value_template="{value}",
                ),
                generic_prefix=None,
                routing=RoutingSpec(
                    dicom_tag=dicom_tag,
                    visible_pixel=VisiblePixelRoute(enabled=True, line_index=0),
                ),
            )
        ],
    )


# Input: `field_name`, sichtbares Label und Textbestandteile.
# Output: Renderplan-Eintrag fuer den bestehenden Pixelrenderer.
# Die Funktion markiert Prefix und Suffix als generische Segmente und das
# API-`value` als PII, ohne Leerzeichen automatisch zu ergaenzen.
def _build_api_render_plan(
    *,
    field_name: str,
    category: str,
    value: str,
    prefix: str,
    suffix: str,
    rotation_degrees: int,
) -> list[dict[str, object]]:
    full_text = f"{prefix}{value}{suffix}"
    return [
        {
            "label": category,
            "category": category,
            "text": full_text,
            "text_segments": [
                {"kind": "generic", "text": prefix},
                {"kind": "pii", "text": value},
                {"kind": "generic", "text": suffix},
            ],
            "identity_field": field_name,
            "region": "corners",
            "rotation_degrees": rotation_degrees,
            "line_index": 0,
        }
    ]


# Input: Runtime-Parameter fuer den bestehenden Runner.
# Output: Vollstaendige Namespace-Konfiguration fuer einen API-Run.
# Die Funktion setzt nur Position und Rotation zufaellig; alle anderen
# Renderoptionen bleiben auf den Pipeline-Defaults.
def _build_runner_args(
    *,
    seed: int,
    input_path: Path,
    schema: IdentifierSchema,
    identity: Identity,
    tag_identity: Identity,
    handwriting_identity: Identity | None,
    handwriting_text_asset_override: dict[str, str] | None,
    visible_render_plan: list[dict[str, object]],
    rotation_degrees: int,
    handwritten: bool,
) -> Namespace:
    return Namespace(
        seed=seed,
        input=str(input_path),
        output_dir=str(DEFAULT_OUTPUT_DIR),
        identifier_schema=str(DEFAULT_IDENTIFIER_SCHEMA_PATH),
        identifier_schema_override=schema,
        identity_override=identity,
        tag_identity_override=tag_identity,
        handwriting_identity_override=handwriting_identity,
        handwriting_text_asset_override=handwriting_text_asset_override,
        visible_render_plan_override=visible_render_plan,
        handwriting_manifest=None,
        handwriting_asset=[],
        handwriting_asset_root=str(DEFAULT_HANDWRITING_ASSET_ROOT),
        handwriting_checkpoint=str(DEFAULT_HANDWRITING_CHECKPOINT_PATH),
        handwriting_checkpoint_sha256=None,
        handwriting_options_json=None,
        handwriting_source_dir=str(DEFAULT_HANDWRITING_SOURCE_DIR),
        handwriting_upstream_commit=None,
        handwriting_runtime_command=None,
        handwriting_container_image=DEFAULT_HANDWRITING_CONTAINER_IMAGE,
        handwriting_generator_command=None,
        rotation_angle=rotation_degrees,
        font_size_pct=100,
        placement_mode="corners",
        font_family=HANDWRITING_FONT_FAMILY if handwritten else "arial",
        text_background=None,
        show_label_boxes="n",
        run_timestamp=None,
    )


# Input: Runner-Pfade und optionaler Exportordner.
# Output: Pfade zu injiziertem Dokument und Ground-Truth-JSON.
# Die Funktion kopiert bei API-Export nur die beiden vertraglichen Dateien und
# laesst alle vollstaendigen Run-Artefakte im normalen `output/`-Runordner.
def _export_api_outputs(
    paths: dict[str, Path],
    output_dir: str | PathLike[str] | None,
) -> tuple[Path, Path]:
    injected_path = paths["output_file"]
    ground_truth_path = paths["output_json"]
    if output_dir is None:
        return injected_path, ground_truth_path

    export_dir = Path(output_dir)
    export_dir.mkdir(parents=True, exist_ok=True)
    exported_injected_path = export_dir / injected_path.name
    exported_ground_truth_path = export_dir / ground_truth_path.name
    if injected_path.resolve() != exported_injected_path.resolve():
        shutil.copy2(injected_path, exported_injected_path)
    if ground_truth_path.resolve() != exported_ground_truth_path.resolve():
        shutil.copy2(ground_truth_path, exported_ground_truth_path)
    return exported_injected_path, exported_ground_truth_path


# Input: API-Parameter fuer Kategorie, Wert, Kontexttexte, Handschriftmodus und Format.
# Output: Pfade zu injiziertem Dokument und Ground-Truth-JSON.
# Die Funktion fuehrt einen normalen DICOM/JPG-Run mit genau einer sichtbaren
# Injektion aus und exportiert optional die zwei Hauptartefakte in `output_dir`.
def inject_function(
    category: str,
    value: str,
    prefix: str,
    suffix: str,
    handwritten: bool,
    documentType: str,
    output_dir: str | PathLike[str] | None = None,
) -> tuple[Path, Path]:
    category, value, prefix, suffix, handwritten, document_type = _validate_api_inputs(
        category,
        value,
        prefix,
        suffix,
        handwritten,
        documentType,
    )
    default_schema = load_identifier_schema(DEFAULT_IDENTIFIER_SCHEMA_PATH)
    field_name, dicom_tag = _resolve_api_field(
        category=category,
        default_schema=default_schema,
    )
    schema = _build_api_schema(
        field_name=field_name,
        category=category,
        dicom_tag=dicom_tag,
        default_schema=default_schema,
    )

    rendered_text = f"{prefix}{value}{suffix}"
    seed = random.SystemRandom().randrange(0, 1_000_000_000)
    rotation_degrees = random.SystemRandom().choice(tuple(ALLOWED_ROTATIONS_DEGREES))
    visible_render_plan = _build_api_render_plan(
        field_name=field_name,
        category=category,
        value=value,
        prefix=prefix,
        suffix=suffix,
        rotation_degrees=rotation_degrees,
    )
    identity = Identity(identity_id=value, seed=seed, fields={field_name: value})
    tag_identity = Identity(identity_id=value, seed=seed, fields={field_name: value})
    handwriting_identity = None
    handwriting_text_asset_override = (
        {"field": field_name, "text": rendered_text} if handwritten else None
    )
    paths = run_pipeline(
        _build_runner_args(
            seed=seed,
            input_path=_select_random_source(document_type),
            schema=schema,
            identity=identity,
            tag_identity=tag_identity,
            handwriting_identity=handwriting_identity,
            handwriting_text_asset_override=handwriting_text_asset_override,
            visible_render_plan=visible_render_plan,
            rotation_degrees=rotation_degrees,
            handwritten=handwritten,
        ),
        now=datetime.now(),
    )
    return _export_api_outputs(paths, output_dir)
