"""Prototype runner: sequence the DICOM/JPG injection stages."""

import hashlib
import shlex
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from injection_pipeline.artifacts.ground_truth import build_record, write_run_artifacts
from injection_pipeline.config.identifier_schema import (
    DEFAULT_IDENTIFIER_SCHEMA_PATH,
    load_identifier_schema,
)
from injection_pipeline.engine.facade import run_document_pixel_injection
from injection_pipeline.engine.handwriting_manifest import (
    apply_handwriting_assets,
    load_handwriting_manifest,
    parse_handwriting_asset_mappings,
)
from injection_pipeline.handwriting import (
    CommandHandwritingGenerator,
    DockerHandwritingGenerator,
    GeneratedHandwritingManifest,
    HandwritingAssetProvider,
    HandwritingGeneratorOptions,
    HandwritingRuntimeConfig,
    extract_required_alphabet,
    load_options_sidecar,
    resolve_options_sidecar,
)
from injection_pipeline.identity.generator import generate_identity
from injection_pipeline.loaders.registry import resolve
from injection_pipeline.models import InjectedDocument
from injection_pipeline.runtime.inputs import (
    derive_example_type,
    resolve_input_path,
)
from injection_pipeline.runtime.options import (
    DEFAULT_HANDWRITING_ASSET_ROOT,
    DEFAULT_HANDWRITING_CHECKPOINT_PATH,
    DEFAULT_HANDWRITING_CONTAINER_IMAGE,
    DEFAULT_HANDWRITING_SOURCE_DIR,
    HANDWRITING_FONT_FAMILY,
)
from injection_pipeline.runtime.planning import (
    build_tag_annotations,
    build_visible_render_plan,
)
from injection_pipeline.runtime.run_layout import build_output_paths, build_run_id
from injection_pipeline.writers.preview import create_annotated_preview


# Input: `path` mit Checkpoint-Datei.
# Output: SHA-256-Hexdigest des Dateiinhalts.
# Die Funktion streamt den Checkpoint nur fuer Handschriftlaeufe ohne expliziten
# Hash und veraendert keine lokalen Artefakte.
def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


# Input: `source_dir` mit gemounteter ScrabbleGAN-Source.
# Output: Gepinnter Upstream-Commit.
# Die Funktion verlangt `.git_commit` oder einen lokalen Git-Checkout und
# erzeugt keinen synthetischen Fallback fuer die Cache-Identitaet.
def _read_handwriting_upstream_commit(source_dir: Path) -> str:
    if not source_dir.exists():
        raise ValueError(f"ScrabbleGAN source directory not found: {source_dir}")

    commit_file = source_dir / ".git_commit"
    if commit_file.exists():
        try:
            commit = commit_file.read_text(encoding="utf-8-sig").strip()
        except UnicodeDecodeError:
            # Windows PowerShell 5 writes `>` as UTF-16 by default.
            commit = commit_file.read_text(encoding="utf-16").strip()
        if commit:
            return commit

    if (source_dir / ".git").exists():
        try:
            output = subprocess.check_output(
                ["git", "-C", str(source_dir), "rev-parse", "HEAD"],
                stderr=subprocess.STDOUT,
                text=True,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            raise ValueError(f"Could not read ScrabbleGAN git commit: {exc}") from exc
        commit = output.strip()
        if commit:
            return commit

    raise ValueError(
        "ScrabbleGAN source metadata missing: provide .git_commit or a .git checkout."
    )


# Input: `args` mit optionalen Handschrift-Runtime-Feldern.
# Output: Normalisierte `HandwritingRuntimeConfig`.
# Die Funktion buendelt CLI-Defaults fuer Checkpoint, Source, Options-Sidecar und
# Asset-Root; Hashes werden nur berechnet, wenn kein expliziter Hash gesetzt ist.
def _build_handwriting_runtime_config(args: Any) -> HandwritingRuntimeConfig:
    checkpoint_path = Path(
        getattr(args, "handwriting_checkpoint", DEFAULT_HANDWRITING_CHECKPOINT_PATH)
    )
    checkpoint_sha256 = getattr(args, "handwriting_checkpoint_sha256", None)
    if checkpoint_sha256 is None:
        checkpoint_sha256 = _sha256_file(checkpoint_path)

    source_dir = Path(
        getattr(args, "handwriting_source_dir", DEFAULT_HANDWRITING_SOURCE_DIR)
    )
    upstream_commit = getattr(args, "handwriting_upstream_commit", None)
    if upstream_commit is None:
        upstream_commit = _read_handwriting_upstream_commit(source_dir)
    options_sidecar_path = resolve_options_sidecar(
        checkpoint_path,
        (
            None
            if getattr(args, "handwriting_options_json", None) is None
            else Path(args.handwriting_options_json)
        ),
    )

    return HandwritingRuntimeConfig(
        checkpoint_path=checkpoint_path,
        checkpoint_sha256=checkpoint_sha256,
        upstream_commit=upstream_commit,
        asset_root=Path(
            getattr(args, "handwriting_asset_root", DEFAULT_HANDWRITING_ASSET_ROOT)
        ),
        source_dir=source_dir,
        options_sidecar_path=options_sidecar_path,
        generator_command=getattr(args, "handwriting_generator_command", None),
    )


# Input: `sidecar_path` mit ScrabbleGAN-Test-/Train-Optionen.
# Output: Cachewirksame Provider-Optionen.
# Die Funktion liest Alphabet und Sidecar-Hash aus demselben Vertrag, den die
# isolierte Batch-Runtime fuer realen ScrabbleGAN-Aufruf verwendet.
def _build_handwriting_generator_options(
    sidecar_path: Path,
) -> HandwritingGeneratorOptions:
    options = load_options_sidecar(sidecar_path)
    return HandwritingGeneratorOptions(
        alphabet=extract_required_alphabet(options),
        options_sha256=_sha256_file(sidecar_path),
        extra={"options_sidecar_name": sidecar_path.name},
    )


# Input: `args` mit optionalem Batch-Command.
# Output: Argumentliste fuer den Provider-Command-Generator.
# Die Funktion erlaubt CLI-Ueberschreibung der isolierten Batch-Runtime und
# nutzt sonst den repo-lokalen ScrabbleGAN-Vertrag.
def _handwriting_runtime_command(args: Any) -> tuple[str, ...] | None:
    raw_command = getattr(args, "handwriting_runtime_command", None)
    if raw_command is None:
        return None
    return tuple(shlex.split(raw_command))


# Input: `args` mit Handschrift-Runtime- und Generatoroptionen.
# Output: Konfigurierter Provider mit Command-Generator.
# Die Funktion startet noch keine externe Runtime; der Generator wird erst bei
# einem Cache-Miss innerhalb der Provider-API aufgerufen.
def _build_handwriting_provider(args: Any) -> HandwritingAssetProvider:
    runtime = _build_handwriting_runtime_config(args)
    if runtime.options_sidecar_path is None:
        raise ValueError("Handwriting options sidecar is required.")
    runtime_command = _handwriting_runtime_command(args)
    generator = (
        CommandHandwritingGenerator(runtime_command)
        if runtime_command is not None
        else DockerHandwritingGenerator(
            image=getattr(
                args,
                "handwriting_container_image",
                DEFAULT_HANDWRITING_CONTAINER_IMAGE,
            ),
            workspace_root=Path.cwd(),
        )
    )
    return HandwritingAssetProvider(
        runtime=runtime,
        options=_build_handwriting_generator_options(runtime.options_sidecar_path),
        generator=generator,
    )


# Input: Renderplan und `generated` Provider-Ergebnis.
# Output: Renderplan mit Handschrift-Asset-Overlays.
# Die Funktion fuehrt Provider-Manifeste ueber dieselbe bestehende Attachment-
# Kette wie explizite `--handwriting-manifest`-Laeufe.
def _apply_generated_handwriting_assets(
    visible_render_plan: list[dict[str, Any]],
    generated: GeneratedHandwritingManifest,
) -> list[dict[str, Any]]:
    return apply_handwriting_assets(
        visible_render_plan,
        load_handwriting_manifest(generated.manifest_path),
        generated.asset_mappings,
    )


# Input: Renderplan nach optionaler Manifest-/Provider-Anreicherung.
# Output: Keine Rueckgabe.
# Die Funktion lehnt `font-family=handwriting` ohne vollstaendige Asset-Abdeckung
# hart ab, damit kein Font-Fallback auf den Pixelpfad durchrutscht.
def _reject_mixed_handwriting_renderers(
    visible_render_plan: list[dict[str, Any]],
) -> None:
    missing_fields = [
        str(item.get("identity_field"))
        for item in visible_render_plan
        if item.get("renderer_type") != "handwriting_asset"
    ]
    if missing_fields:
        raise ValueError(
            "font-family='handwriting' requires handwriting assets for every "
            f"visible field; missing {missing_fields}."
        )


# Input: `args` mit Seed, Identifier-Schema und Handschrift-Runtime-Optionen.
# Output: Provider-Ergebnis mit Manifestpfad und Asset-Mappings.
# Die Funktion erzeugt dieselbe Faker-Identitaet wie ein normaler Run und ruft
# nur die Handschrift-Provider-API auf, ohne Dokumente zu laden oder zu injizieren.
def generate_handwriting_assets(args: Any) -> GeneratedHandwritingManifest:
    identifier_schema_path = Path(
        getattr(args, "identifier_schema", DEFAULT_IDENTIFIER_SCHEMA_PATH)
    )
    identifier_schema = load_identifier_schema(identifier_schema_path)
    identity = generate_identity(args.seed, identifier_schema)
    generated = _build_handwriting_provider(args).resolve_assets(
        identity,
        identifier_schema,
    )
    print(
        f"Handwriting manifest: {generated.manifest_path}\n"
        f"Generated assets: {len(generated.generated_asset_ids)}\n"
        f"Cache hits: {len(generated.cache_hit_asset_ids)}"
    )
    for identity_field, asset_id in sorted(generated.asset_mappings.items()):
        print(f"{identity_field}={asset_id}")
    return generated


# Input: `args`, Identitaet, Schema und sichtbarer Renderplan.
# Output: Renderplan mit optionalen Handschrift-Assets.
# Die Funktion bewahrt explizite Manifest-/Mapping-Laeufe und verwendet den
# Provider automatisch nur fuer `font_family='handwriting'`.
def _resolve_handwriting_render_plan(
    args: Any,
    identity: Any,
    identifier_schema: Any,
    visible_render_plan: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if args.handwriting_manifest is not None:
        visible_render_plan = apply_handwriting_assets(
            visible_render_plan,
            load_handwriting_manifest(Path(args.handwriting_manifest)),
            parse_handwriting_asset_mappings(args.handwriting_asset),
        )
    elif args.font_family == HANDWRITING_FONT_FAMILY:
        visible_render_plan = _apply_generated_handwriting_assets(
            visible_render_plan,
            _build_handwriting_provider(args).resolve_assets(
                identity,
                identifier_schema,
            ),
        )

    if args.font_family == HANDWRITING_FONT_FAMILY:
        _reject_mixed_handwriting_renderers(visible_render_plan)
    return visible_render_plan


# Input: `args` with validated CLI or interactive run parameters, optional `now`.
# Output: Keine Rueckgabe; schreibt Run-Artefakte auf das Dateisystem.
# Die Funktion orchestriert die Stufen ueber registrierte Formatadapter; `now`
# fixiert den Run-ID-Zeitstempel.
def run(args: Any, now: datetime | None = None) -> None:
    run_timestamp = datetime.now() if now is None else now
    input_path, was_auto_selected = resolve_input_path(args.input, args.seed)
    if was_auto_selected:
        print(f"Auto-selected input: {input_path}")

    identifier_schema_path = Path(
        getattr(args, "identifier_schema", DEFAULT_IDENTIFIER_SCHEMA_PATH)
    )
    identifier_schema = load_identifier_schema(identifier_schema_path)
    loader, writer = resolve(input_path)
    document_type = loader.format_id
    example_type = derive_example_type(input_path)
    run_id = build_run_id(
        filetype=document_type,
        run_timestamp=run_timestamp,
        seed=args.seed,
        rotation_degrees=args.rotation_angle,
        placement_mode=args.placement_mode,
        font_size_pct=args.font_size_pct,
        font_family=args.font_family,
        text_background=args.text_background,
    )
    output_paths = build_output_paths(
        Path(args.output_dir),
        run_id,
        input_path.stem,
        writer.output_suffix,
    )

    identity_a = generate_identity(args.seed, identifier_schema)
    visible_render_plan = build_visible_render_plan(
        identity=identity_a,
        schema=identifier_schema,
        rotation_degrees=args.rotation_angle,
        placement_mode=args.placement_mode,
    )
    visible_render_plan = _resolve_handwriting_render_plan(
        args,
        identity_a,
        identifier_schema,
        visible_render_plan,
    )

    output_paths["run_dir"].mkdir(parents=True, exist_ok=True)
    source_document = loader.load(input_path)
    tag_plan = {
        annotation.tag_keyword: annotation
        for annotation in build_tag_annotations(
            identity=identity_a,
            schema=identifier_schema,
            input_path=input_path,
            output_path=output_paths["output_file"],
        )
    }
    tag_annotations = writer.inject_native_metadata(source_document, tag_plan)
    rendered_frame, pixel_result = run_document_pixel_injection(
        document=source_document,
        visible_injections=visible_render_plan,
        preview_path=output_paths["preview_file"],
        seed=args.seed,
        rotation_degrees=args.rotation_angle,
        font_size_pct=args.font_size_pct,
        placement_mode=args.placement_mode,
        font_family=args.font_family,
        text_background=args.text_background,
    )
    injected_document = InjectedDocument(
        source=source_document,
        rendered_frame=rendered_frame,
        native=source_document.native,
        tag_annotations=tag_annotations,
        box_annotations=pixel_result["box_annotations"],
        output_context=None,
    )
    writer.write(injected_document, output_paths["output_file"])

    create_annotated_preview(
        source_path=pixel_result["preview_file"] or output_paths["preview_file"],
        box_annotations=[
            annotation.model_dump(mode="json")
            for annotation in pixel_result["box_annotations"]
        ],
        output_path=output_paths["annotated_preview_file"],
        title=input_path.stem,
        show_label_boxes=args.show_label_boxes == "y",
    )
    record = build_record(
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
        identifier_schema=identifier_schema,
        source_dicom_context=source_document.context,
        output_dicom_context=injected_document.output_context,
        tag_annotations=injected_document.tag_annotations,
        box_annotations=injected_document.box_annotations,
        visible_render_plan=visible_render_plan,
        pixel_result=pixel_result,
    )
    write_run_artifacts(record, output_paths)

    print(
        f"Run {run_id} written to {output_paths['run_dir']}\n"
        f"Injected {len(tag_annotations)} tags into {output_paths['output_file']}\n"
        f"Ground truth written to {output_paths['output_json']}\n"
        f"Preview:            {output_paths['preview_file']}\n"
        f"Annotated preview:  {output_paths['annotated_preview_file']}"
    )
    print(f"Pixel injection status: {pixel_result['status']}")
