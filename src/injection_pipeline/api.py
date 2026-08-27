"""Public API helpers for single synthetic PII injections."""

import random
import re
import shutil
from argparse import Namespace
from collections.abc import Mapping, Sequence
from datetime import datetime
from os import PathLike
from pathlib import Path
from typing import Protocol

from pydantic import ValidationError

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
from injection_pipeline.loaders.pdf import PdfLoader
from injection_pipeline.models.identity import Identity
from injection_pipeline.pdf.models import (
    PdfMakeArtifacts,
    PdfMakeImageInput,
    PdfMakeTextInput,
    PdfTemplate,
)
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
from injection_pipeline.runtime.seeding import derive_seed

_DOCUMENT_TYPE_EXTENSIONS: dict[str, tuple[str, ...]] = {
    "dcm": (".dcm",),
    "jpg": (".jpg", ".jpeg"),
}
_DOCUMENT_TYPE_INPUT_DIRS: dict[str, Path] = {
    "dcm": DEFAULT_DICOM_DIR,
    "jpg": DEFAULT_IMAGE_DIR,
}
_NONDETERMINISTIC_SEED_UPPER_BOUND = 2**63

PdfMakeImageInputLike = PdfMakeImageInput | Mapping[str, object]
PdfMakeTextInputLike = PdfMakeTextInput | Mapping[str, object]


class _MakePdfComposition(Protocol):
    """Callable contract for the PDF make writer integration point."""

    def __call__(
        self,
        *,
        images: list[PdfMakeImageInput],
        texts: list[PdfMakeTextInput],
        template: PdfTemplate,
        output_dir: Path,
        seed: int,
    ) -> PdfMakeArtifacts: ...


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
# Input: Dokumenttyp und optionaler deterministischer Seed.
# Output: Ausgewaehlter lokaler Quellpfad.
# Ohne Seed bleibt die bestehende SystemRandom-Auswahl erhalten; mit Seed wird
# ein benannter Stream und eine totale Kandidatensortierung verwendet.
def _select_random_source(document_type: str, seed: int | None = None) -> Path:
    input_dir = _DOCUMENT_TYPE_INPUT_DIRS[document_type]
    allowed_extensions = _DOCUMENT_TYPE_EXTENSIONS[document_type]
    if not input_dir.exists():
        raise ValueError(
            f"No default input directory found for {document_type}: {input_dir}"
        )
    candidates = sorted(
        [
            path
            for path in input_dir.iterdir()
            if path.is_file() and path.suffix.casefold() in allowed_extensions
        ],
        key=lambda path: (str(path).casefold(), str(path)),
    )
    if not candidates:
        raise ValueError(
            f"No default {document_type} input files found in {input_dir}."
        )
    if seed is None:
        return random.SystemRandom().choice(candidates)
    rng = random.Random(derive_seed(seed, "api_input_selection"))
    return rng.choice(candidates)


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
    handwriting_ink_color: str = "auto",
    handwriting_contrast_mode: str = "none",
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
        handwriting_ink_color=handwriting_ink_color,
        handwriting_contrast_mode=handwriting_contrast_mode,
        show_label_boxes="n",
        run_timestamp=None,
    )


# Input: Runner-Pfade und optionaler Exportordner.
# Output: Pfade zu injiziertem Dokument und Ground-Truth-JSON.
# Die Funktion kopiert bei API-Export nur die beiden vertraglichen Dateien und
# laesst alle vollstaendigen Run-Artefakte im normalen `output/`-Runordner.
def _export_api_outputs(
    paths: dict[str, Path],
    output_dir: Path | None,
) -> tuple[Path, Path]:
    injected_path = paths["output_file"]
    ground_truth_path = paths["output_json"]
    if output_dir is None:
        return injected_path, ground_truth_path

    export_dir = output_dir
    export_dir.mkdir(parents=True, exist_ok=True)
    exported_injected_path = export_dir / injected_path.name
    exported_ground_truth_path = export_dir / ground_truth_path.name
    if injected_path.resolve() != exported_injected_path.resolve():
        shutil.copy2(injected_path, exported_injected_path)
    if ground_truth_path.resolve() != exported_ground_truth_path.resolve():
        shutil.copy2(ground_truth_path, exported_ground_truth_path)
    return exported_injected_path, exported_ground_truth_path


# Input: Optionaler API-Exportordner.
# Output: Normalisierter Exportordner oder `None`.
# Die Funktion validiert den Exportpfad vor dem eigentlichen Pipeline-Lauf,
# damit ungueltige Ziele keine DICOM-, JPG- oder Handschrift-Artefakte erzeugen.
def _validate_api_output_dir(
    output_dir: str | PathLike[str] | None,
) -> Path | None:
    if output_dir is None:
        return None
    try:
        output_path = Path(output_dir)
    except TypeError as exc:
        raise ValueError("output_dir must be a str or path-like value.") from exc
    if output_path.exists() and not output_path.is_dir():
        raise ValueError(f"output_dir must be a directory path: {output_path}")
    return output_path


# Input: Textbestandteile eines make_pdf-Eintrags und sein API-Feldpfad.
# Output: Keine Rueckgabe; ungueltige Werte fuehren zu ValueError.
# Die Funktion spiegelt den Text-Validierungsrand von `inject_function` fuer
# direkte PDF-Texte und uebernommene Bildannotationen.
def _validate_make_pdf_text_parts(
    *,
    category: str,
    value: str,
    prefix: str,
    suffix: str,
    field_path: str,
) -> None:
    if not isinstance(category, str) or category.strip() == "":
        raise ValueError(f"{field_path}.category must be a non-empty string.")
    if not isinstance(value, str) or value == "":
        raise ValueError(f"{field_path}.value must be a non-empty string.")
    if not isinstance(prefix, str):
        raise ValueError(f"{field_path}.prefix must be a string.")
    if not isinstance(suffix, str):
        raise ValueError(f"{field_path}.suffix must be a string.")


# Input: `values` mit Text-API-Modellen oder Mapping-Daten.
# Output: Liste streng validierter `PdfMakeTextInput`-Modelle.
# Die Funktion bildet den Validierungsrand fuer direkte PDF-Texte und bricht
# leere oder strukturell ungueltige Listen vor jedem Schreibzugriff ab.
def _validate_make_pdf_texts(
    values: Sequence[PdfMakeTextInputLike],
) -> list[PdfMakeTextInput]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        raise ValueError("texts must be a non-empty sequence of text inputs.")

    texts: list[PdfMakeTextInput] = []
    for index, value in enumerate(values):
        if isinstance(value, PdfMakeTextInput):
            text = value
        elif isinstance(value, Mapping):
            try:
                text = PdfMakeTextInput.model_validate(value)
            except ValidationError as exc:
                raise ValueError(f"texts[{index}] is invalid: {exc}") from exc
        else:
            raise ValueError(
                f"texts[{index}] must be a PdfMakeTextInput or mapping data."
            )
        _validate_make_pdf_text_parts(
            category=text.category,
            value=text.value,
            prefix=text.prefix,
            suffix=text.suffix,
            field_path=f"texts[{index}]",
        )
        texts.append(text)

    if not texts:
        raise ValueError("texts must contain at least one item.")
    return texts


# Input: `values` mit Bild-API-Modellen oder Mapping-Daten.
# Output: Liste streng validierter `PdfMakeImageInput`-Modelle.
# Die Funktion prueft Bildpfade und Annotationen vor dem Writer-Aufruf, damit
# fehlende Dateien oder leere Annotationen nicht erst beim PDF-Schreiben auffallen.
def _validate_make_pdf_images(
    values: Sequence[PdfMakeImageInputLike],
) -> list[PdfMakeImageInput]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        raise ValueError("images must be a non-empty sequence of image inputs.")

    images: list[PdfMakeImageInput] = []
    for index, value in enumerate(values):
        if isinstance(value, PdfMakeImageInput):
            image = value
        elif isinstance(value, Mapping):
            try:
                image = PdfMakeImageInput.model_validate(value)
            except ValidationError as exc:
                raise ValueError(f"images[{index}] is invalid: {exc}") from exc
        else:
            raise ValueError(
                f"images[{index}] must be a PdfMakeImageInput or mapping data."
            )

        if not image.annotations:
            raise ValueError(
                f"images[{index}].annotations must contain at least one item."
            )
        for annotation_index, annotation in enumerate(image.annotations):
            field_path = f"images[{index}].annotations[{annotation_index}]"
            _validate_make_pdf_text_parts(
                category=annotation.category,
                value=annotation.value,
                prefix=annotation.prefix,
                suffix=annotation.suffix,
                field_path=field_path,
            )
            if annotation.rendered_text == "":
                raise ValueError(f"{field_path}.rendered_text must be non-empty.")
        if not image.path.exists():
            raise FileNotFoundError(
                f"images[{index}].path does not exist: {image.path}"
            )
        if not image.path.is_file():
            raise ValueError(f"images[{index}].path must be a file: {image.path}")
        images.append(image)

    if not images:
        raise ValueError("images must contain at least one item.")
    return images


# Input: `pdf`, Bildquellen und `output_dir` aus der Public API.
# Output: Normalisierte PDF- und Ausgabe-Pfade.
# Die Funktion prueft die PDF vor jedem Schreibzugriff und stellt sicher, dass
# keine PDF- oder Bildquelle einen vorgesehenen Ausgabe-Pfad aliasiert und
# `output_dir` nicht auf eine bestehende Datei zeigt.
def _validate_make_pdf_paths(
    pdf: str | PathLike[str],
    output_dir: str | PathLike[str],
    images: Sequence[PdfMakeImageInput] = (),
) -> tuple[Path, Path]:
    try:
        pdf_path = Path(pdf)
    except TypeError as exc:
        raise ValueError("pdf must be a str or path-like value.") from exc
    try:
        output_dir_path = Path(output_dir)
    except TypeError as exc:
        raise ValueError("output_dir must be a str or path-like value.") from exc

    if not pdf_path.exists():
        raise FileNotFoundError(f"pdf does not exist: {pdf_path}")
    if not pdf_path.is_file():
        raise ValueError(f"pdf must be a file: {pdf_path}")
    if output_dir_path.exists() and not output_dir_path.is_dir():
        raise ValueError(f"output_dir must be a directory path: {output_dir_path}")
    output_targets = (
        output_dir_path / "pdf_make.pdf",
        output_dir_path / "pdf_make_annotated.pdf",
        output_dir_path / "pdf_make_annotations.json",
    )
    sources = [("PDF template", pdf_path)]
    sources.extend(
        (f"PDF make image source {index}", image.path)
        for index, image in enumerate(images)
    )
    for source_label, source_path in sources:
        if any(_paths_alias(source_path, target) for target in output_targets):
            raise ValueError(
                f"{source_label} and make_pdf output paths must be different: "
                f"{source_path}."
            )
    return pdf_path, output_dir_path


# Input: Zwei Datei- oder Zielpfade.
# Output: `True`, wenn beide Pfade dasselbe Dateisystemobjekt bezeichnen.
# Die Prüfung deckt normale Pfadaliasse sowie bereits existierende Hardlinks
# ab, ohne nicht vorhandene Ausgabeziele vorzeitig anzulegen.
def _paths_alias(first: Path, second: Path) -> bool:
    if first.resolve() == second.resolve():
        return True
    if not first.exists() or not second.exists():
        return False
    try:
        return first.samefile(second)
    except OSError:
        return False


# Input: Optionaler API-Seed.
# Output: Expliziter Integer-Seed fuer Layout, Rotation und Seitenumbrueche.
# Die Funktion erzeugt bei `None` einen nichtdeterministischen Seed, der an den
# Writer weitergereicht und dadurch im Sidecar dokumentiert wird.
def _resolve_make_pdf_seed(seed: int | None) -> int:
    if seed is None:
        return random.SystemRandom().randrange(0, _NONDETERMINISTIC_SEED_UPPER_BOUND)
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ValueError("seed must be an integer or None.")
    return seed


# Input: Kein fachlicher Parameter; der Writer wird ueber seinen Modulpfad geladen.
# Output: Callable `make_pdf_composition` fuer die PDF-Komposition.
# Der lokale Import haelt den API-Import leichtgewichtig und bleibt fuer Mypy
# pruefbar, damit Keyword-Vertragsbrueche nicht durch Casts verdeckt werden.
def _load_make_pdf_composition() -> _MakePdfComposition:
    from injection_pipeline.writers.pdf_make import make_pdf_composition

    return make_pdf_composition


# Input: Sequenzen aus Bild- und Textdaten, Quell-PDF, Ausgabeordner und Seed.
# Output: `PdfMakeArtifacts` mit PDF-Pfaden und Annotation-Sidecar.
# Die Funktion validiert die Public-API-Daten vorab, laedt das PDF-Template per
# Adapter und delegiert Layout, Rotation, Seitenumbrueche und Schreiben an den Writer.
def make_pdf(
    images: Sequence[PdfMakeImageInputLike],
    texts: Sequence[PdfMakeTextInputLike],
    pdf: str | PathLike[str],
    output_dir: str | PathLike[str],
    *,
    seed: int | None = None,
) -> PdfMakeArtifacts:
    validated_images = _validate_make_pdf_images(images)
    validated_texts = _validate_make_pdf_texts(texts)
    pdf_path, output_dir_path = _validate_make_pdf_paths(
        pdf,
        output_dir,
        validated_images,
    )
    resolved_seed = _resolve_make_pdf_seed(seed)
    template = PdfLoader().load(pdf_path)
    make_pdf_composition = _load_make_pdf_composition()

    return make_pdf_composition(
        images=validated_images,
        texts=validated_texts,
        template=template,
        output_dir=output_dir_path,
        seed=resolved_seed,
    )


# Input: API-Parameter sowie optionale deterministische Seed-, Quellen-,
# Rotations- und Zeitparameter.
# Output: Pfade zu injiziertem Dokument und Ground-Truth-JSON.
# Die Funktion fuehrt einen normalen DICOM/JPG-Run mit genau einer sichtbaren
# Injektion aus. Ohne optionale Determinismusparameter bleibt das Legacy-
# Verhalten mit SystemRandom und aktueller Uhrzeit erhalten.
def inject_function(
    category: str,
    value: str,
    prefix: str,
    suffix: str,
    handwritten: bool,
    documentType: str,
    output_dir: str | PathLike[str] | None = None,
    handwriting_ink_color: str = "auto",
    handwriting_contrast_mode: str = "none",
    *,
    seed: int | None = None,
    input_path: str | PathLike[str] | None = None,
    rotation_degrees: int | None = None,
    run_timestamp: datetime | None = None,
) -> tuple[Path, Path]:
    category, value, prefix, suffix, handwritten, document_type = _validate_api_inputs(
        category,
        value,
        prefix,
        suffix,
        handwritten,
        documentType,
    )
    validated_output_dir = _validate_api_output_dir(output_dir)
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
    resolved_seed = (
        random.SystemRandom().randrange(0, _NONDETERMINISTIC_SEED_UPPER_BOUND)
        if seed is None
        else seed
    )
    if not isinstance(resolved_seed, int) or isinstance(resolved_seed, bool):
        raise ValueError("seed must be an integer.")
    if rotation_degrees is None:
        if seed is None:
            resolved_rotation = random.SystemRandom().choice(
                tuple(ALLOWED_ROTATIONS_DEGREES)
            )
        else:
            rotation_rng = random.Random(derive_seed(resolved_seed, "api_rotation"))
            resolved_rotation = rotation_rng.choice(tuple(ALLOWED_ROTATIONS_DEGREES))
    else:
        if rotation_degrees not in ALLOWED_ROTATIONS_DEGREES:
            raise ValueError(
                "rotation_degrees must be one of: "
                f"{', '.join(str(value) for value in ALLOWED_ROTATIONS_DEGREES)}."
            )
        resolved_rotation = rotation_degrees
    resolved_input = (
        Path(input_path)
        if input_path is not None
        else _select_random_source(
            document_type, resolved_seed if seed is not None else None
        )
    )
    visible_render_plan = _build_api_render_plan(
        field_name=field_name,
        category=category,
        value=value,
        prefix=prefix,
        suffix=suffix,
        rotation_degrees=resolved_rotation,
    )
    identity = Identity(
        identity_id=value, seed=resolved_seed, fields={field_name: value}
    )
    tag_identity = Identity(
        identity_id=value, seed=resolved_seed, fields={field_name: value}
    )
    handwriting_identity = None
    handwriting_text_asset_override = (
        {"field": field_name, "text": rendered_text} if handwritten else None
    )
    paths = run_pipeline(
        _build_runner_args(
            seed=resolved_seed,
            input_path=resolved_input,
            schema=schema,
            identity=identity,
            tag_identity=tag_identity,
            handwriting_identity=handwriting_identity,
            handwriting_text_asset_override=handwriting_text_asset_override,
            visible_render_plan=visible_render_plan,
            rotation_degrees=resolved_rotation,
            handwritten=handwritten,
            handwriting_ink_color=handwriting_ink_color,
            handwriting_contrast_mode=handwriting_contrast_mode,
        ),
        now=datetime.now() if run_timestamp is None else run_timestamp,
    )
    return _export_api_outputs(paths, validated_output_dir)
