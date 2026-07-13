"""Prototype runner: sequence the DICOM/JPG injection stages."""

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
from injection_pipeline.identity.generator import generate_identity
from injection_pipeline.loaders.registry import resolve
from injection_pipeline.models import InjectedDocument
from injection_pipeline.runtime.inputs import (
    derive_example_type,
    resolve_input_path,
)
from injection_pipeline.runtime.planning import (
    build_tag_annotations,
    build_visible_render_plan,
)
from injection_pipeline.runtime.run_layout import build_output_paths, build_run_id
from injection_pipeline.writers.preview import create_annotated_preview


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
    if args.handwriting_manifest is not None:
        visible_render_plan = apply_handwriting_assets(
            visible_render_plan,
            load_handwriting_manifest(Path(args.handwriting_manifest)),
            parse_handwriting_asset_mappings(args.handwriting_asset),
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
