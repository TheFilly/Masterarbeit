"""Command-line entrypoints for isolated ScrabbleGAN batch generation."""

import argparse
import json
from pathlib import Path

from .hashing import sha256_file
from .manifest import load_input_manifest, write_output_manifest
from .masks import build_asset_images
from .render import read_source_commit, render_raw_asset
from .validate import validate_checkpoint, validate_output_manifest

_SCRABBLEGAN_REPO_URL = "https://github.com/amzn/convolutional-handwriting-gan"


# Input: optionale CLI-Argumentliste fuer Tests oder `None` fuer sys.argv.
# Output: Pfad zum geschriebenen Output-Manifest.
# Die Funktion fuehrt einen Batch-Renderlauf aus, schreibt nur erfolgreiche
# Assets ins Manifest und protokolliert fehlgeschlagene Assets separat.
def run_render(argv=None):
    # type: (list) -> Path
    parser = _build_render_parser()
    args = parser.parse_args(argv)

    input_path = Path(args.input)
    output_root = Path(args.output_root)
    run_dir = output_root / args.run_id
    raw_dir = run_dir / "raw"
    image_dir = run_dir / "images"
    mask_dir = run_dir / "masks"
    manifest_path = run_dir / "manifest.jsonl"
    failures_path = run_dir / "failures.jsonl"

    source_dir = Path(args.source_dir)
    checkpoint_path = Path(args.checkpoint)
    validate_checkpoint(checkpoint_path, args.checkpoint_sha256)
    source_commit = read_source_commit(source_dir)
    records = load_input_manifest(input_path)

    output_records = []
    failures = []
    for record in records:
        try:
            output_record = _render_one_record(
                record=record,
                run_dir=run_dir,
                raw_dir=raw_dir,
                image_dir=image_dir,
                mask_dir=mask_dir,
                source_dir=source_dir,
                source_commit=source_commit,
                checkpoint_path=checkpoint_path,
                checkpoint_sha256=args.checkpoint_sha256,
                generator_command=args.generator_command,
                fake_renderer=args.fake_renderer,
            )
            output_records.append(output_record)
        except Exception as exc:
            failures.append(
                {
                    "asset_id": record.get("asset_id"),
                    "field": record.get("field"),
                    "text": record.get("text"),
                    "error": str(exc),
                }
            )

    if failures:
        _write_jsonl(failures, failures_path)
    if not output_records:
        raise ValueError("No handwriting assets were generated successfully.")
    write_output_manifest(output_records, manifest_path)
    validate_output_manifest(manifest_path, checkpoint_path, args.checkpoint_sha256)
    return manifest_path


# Input: optionale CLI-Argumentliste fuer Tests oder `None` fuer sys.argv.
# Output: Prozess-Statuscode.
# Die Funktion validiert ein vorhandenes Output-Manifest fuer nachgelagerte
# Injection-Laeufe.
def run_validate(argv=None):
    # type: (list) -> int
    parser = _build_validate_parser()
    args = parser.parse_args(argv)
    validate_output_manifest(
        Path(args.manifest), Path(args.checkpoint), args.checkpoint_sha256
    )
    return 0


# Input: Keine Parameter.
# Output: Keine Rueckgabe.
# Die Funktion stellt die Modul-CLI mit Subcommands fuer Container-Nutzung bereit.
def main():
    # type: () -> None
    parser = argparse.ArgumentParser(description="ScrabbleGAN handwriting tooling")
    subparsers = parser.add_subparsers(dest="command")
    _build_render_parser(subparsers=subparsers)
    _build_validate_parser(subparsers=subparsers)
    args = parser.parse_args()

    if args.command == "render":
        run_render(_namespace_to_argv(args, "render"))
        return
    if args.command == "validate":
        run_validate(_namespace_to_argv(args, "validate"))
        return
    parser.print_help()
    raise SystemExit(2)


# Input: `subparsers` optional fuer die Modul-CLI.
# Output: argparse-Parser fuer den Render-Befehl.
# Die Funktion definiert den stabilen v1-CLI-Vertrag.
def _build_render_parser(subparsers=None):
    # type: (object) -> argparse.ArgumentParser
    if subparsers is None:
        parser = argparse.ArgumentParser(description="Render ScrabbleGAN assets")
    else:
        parser = subparsers.add_parser(
            "render", description="Render ScrabbleGAN assets"
        )
    parser.add_argument("--input", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--source-dir", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--checkpoint-sha256", required=True)
    parser.add_argument("--generator-command", default=None)
    parser.add_argument("--fake-renderer", action="store_true")
    return parser


# Input: `subparsers` optional fuer die Modul-CLI.
# Output: argparse-Parser fuer den Validate-Befehl.
# Die Funktion definiert die unabhaengige Manifest-Pruefung vor der Injection.
def _build_validate_parser(subparsers=None):
    # type: (object) -> argparse.ArgumentParser
    if subparsers is None:
        parser = argparse.ArgumentParser(description="Validate ScrabbleGAN manifest")
    else:
        parser = subparsers.add_parser(
            "validate", description="Validate ScrabbleGAN manifest"
        )
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--checkpoint-sha256", required=True)
    return parser


# Input: Validierter Input-Record und Render-Kontext.
# Output: Output-Manifest-Record fuer ein erfolgreiches Asset.
# Die Funktion orchestriert Rohrendering, Normalisierung, Hashing und relative
# Pfade fuer genau einen Batch-Eintrag.
def _render_one_record(
    record,
    run_dir,
    raw_dir,
    image_dir,
    mask_dir,
    source_dir,
    source_commit,
    checkpoint_path,
    checkpoint_sha256,
    generator_command,
    fake_renderer,
):
    # type: (dict, Path, Path, Path, Path, Path, str, Path, str, str, bool) -> dict
    asset_id = record["asset_id"]
    raw_path = raw_dir / f"{asset_id}-raw.png"
    image_path = image_dir / f"{asset_id}.png"
    mask_path = mask_dir / f"{asset_id}-mask.png"

    render_raw_asset(
        record=record,
        raw_path=raw_path,
        source_dir=source_dir,
        checkpoint_path=checkpoint_path,
        generator_command=generator_command,
        fake_renderer=fake_renderer,
    )
    metadata = build_asset_images(
        raw_path=raw_path,
        image_path=image_path,
        mask_path=mask_path,
        ink_color=record["ink_color"],
        background=record["background"],
    )

    output_record = {
        "asset_id": asset_id,
        "field": record["field"],
        "text": record["text"],
        "image_path": _relative_posix(run_dir, image_path),
        "mask_path": _relative_posix(run_dir, mask_path),
        "image_sha256": sha256_file(image_path),
        "mask_sha256": sha256_file(mask_path),
        "checkpoint_sha256": checkpoint_sha256,
        "scrabblegan_repo_url": _SCRABBLEGAN_REPO_URL,
        "scrabblegan_commit": source_commit,
        "ink_color": record["ink_color"],
        "background": record["background"],
        "seed": record["seed"],
        "ink_bbox": metadata["ink_bbox"],
        "image_size": metadata["image_size"],
    }
    return output_record


# Input: Records und Zielpfad fuer lokale Fehlerlogs.
# Output: Keine Rueckgabe.
# Die Funktion schreibt Fehler in ein separates JSONL, das nicht vom
# Injection-Prototyp konsumiert wird.
def _write_jsonl(records, path):
    # type: (list, Path) -> None
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, sort_keys=True))
            fh.write("\n")


# Input: Basisordner und Zielpfad.
# Output: POSIX-artiger relativer Pfad fuer Manifeste.
# Die Funktion verhindert absolute lokale Pfade im Output-Vertrag.
def _relative_posix(root, path):
    # type: (Path, Path) -> str
    return path.relative_to(root).as_posix()


# Input: argparse-Namespace aus der Subcommand-CLI und Befehlsname.
# Output: Flache Argumentliste fuer die bestehenden Test-/Entry-Funktionen.
# Die Funktion vermeidet doppelte Ausfuehrungslogik zwischen Modul-CLI und
# direkten `run_*`-Funktionen.
def _namespace_to_argv(args, command):
    # type: (argparse.Namespace, str) -> list
    argv = []
    for key, value in sorted(vars(args).items()):
        if key == "command" or value is None:
            continue
        if isinstance(value, bool):
            if value:
                argv.append("--{}".format(key.replace("_", "-")))
            continue
        argv.extend(["--{}".format(key.replace("_", "-")), str(value)])
    return argv


if __name__ == "__main__":
    main()
