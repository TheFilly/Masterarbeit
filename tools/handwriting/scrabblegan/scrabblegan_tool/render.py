"""Rendering adapter around a mounted ScrabbleGAN checkout."""

import random
import shlex
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw


# Input: `source_dir` mit gemounteter ScrabbleGAN-Source.
# Output: Commit-String fuer Manifest-Metadaten.
# Die Funktion bevorzugt eine explizite `.git_commit`-Datei und faellt auf
# `git rev-parse` zurueck, wenn ein Checkout mit `.git` vorhanden ist.
def read_source_commit(source_dir):
    # type: (Path) -> str
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

    git_dir = source_dir / ".git"
    if git_dir.exists():
        try:
            output = subprocess.check_output(
                ["git", "-C", str(source_dir), "rev-parse", "HEAD"],
                stderr=subprocess.STDOUT,
            )
            return output.decode("utf-8").strip()
        except (subprocess.CalledProcessError, OSError) as exc:
            raise ValueError(
                f"Could not read ScrabbleGAN git commit: {exc}"
            ) from exc

    raise ValueError(
        "ScrabbleGAN source metadata missing: provide .git_commit or a .git checkout."
    )


# Input: ein validierter Manifest-Record und Zielpfad fuer rohe Generatorausgabe.
# Output: Keine Rueckgabe.
# Die Funktion ruft entweder einen Fake-Renderer fuer Tests oder den gemounteten
# ScrabbleGAN-Generator ueber eine Command-Template-Schnittstelle auf.
def render_raw_asset(
    record,
    raw_path,
    source_dir,
    checkpoint_path,
    options_sidecar_path=None,
    generator_command=None,
    fake_renderer=False,
):
    # type: (dict, Path, Path, Path, Path | None, str, bool) -> None
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    if fake_renderer:
        _render_fake_asset(record, raw_path)
        return

    words = _split_words(record["text"])
    if len(words) == 1:
        _render_single_word(
            record=record,
            text=words[0],
            raw_path=raw_path,
            source_dir=source_dir,
            checkpoint_path=checkpoint_path,
            options_sidecar_path=options_sidecar_path,
            generator_command=generator_command,
        )
    else:
        word_paths = []
        for index, word in enumerate(words, start=1):
            word_path = raw_path.parent / f"{raw_path.stem}-word-{index}.png"
            _render_single_word(
                record=record,
                text=word,
                raw_path=word_path,
                source_dir=source_dir,
                checkpoint_path=checkpoint_path,
                options_sidecar_path=options_sidecar_path,
                generator_command=generator_command,
            )
            word_paths.append(word_path)
        _compose_word_images(word_paths, raw_path, record["seed"], record["asset_id"])

    if not raw_path.exists():
        raise ValueError(f"ScrabbleGAN command did not write raw output: {raw_path}")


# Input: Render-Record, Worttext, Zielpfad, Source, Checkpoint und Optionen.
# Output: Keine Rueckgabe.
# Die Funktion fuehrt genau einen upstream Single-Text-Wrapper-Aufruf aus und
# prueft, dass das erwartete PNG geschrieben wurde.
def _render_single_word(
    record,
    text,
    raw_path,
    source_dir,
    checkpoint_path,
    options_sidecar_path,
    generator_command,
):
    # type: (dict, str, Path, Path, Path, Path | None, str) -> None
    command = _build_generator_command(
        record=record,
        text=text,
        raw_path=raw_path,
        source_dir=source_dir,
        checkpoint_path=checkpoint_path,
        options_sidecar_path=options_sidecar_path,
        generator_command=generator_command,
    )
    subprocess.check_call(command, cwd=str(source_dir))
    if not raw_path.exists():
        raise ValueError(f"ScrabbleGAN command did not write raw output: {raw_path}")


# Input: Render-Record, Worttext, Zielpfad, Source, Checkpoint und optionale Template.
# Output: Argumentliste fuer `subprocess`.
# Die Funktion nutzt standardmaessig den lokalen `generate_single.py`-Wrapper
# und erlaubt projektspezifische Templates ueber stabile Platzhalter.
def _build_generator_command(
    record,
    text,
    raw_path,
    source_dir,
    checkpoint_path,
    options_sidecar_path,
    generator_command,
):
    # type: (dict, str, Path, Path, Path, Path | None, str) -> list
    placeholders = {
        "text": text,
        "seed": str(record["seed"]),
        "output": str(raw_path),
        "source_dir": str(source_dir),
        "checkpoint": str(checkpoint_path),
        "options_json": (
            "" if options_sidecar_path is None else str(options_sidecar_path)
        ),
        "asset_id": record["asset_id"],
        "field": record["field"],
    }
    if generator_command:
        return [part.format(**placeholders) for part in shlex.split(generator_command)]

    if options_sidecar_path is None:
        raise ValueError("ScrabbleGAN options sidecar is required for real rendering.")
    generate_py = (
        Path(__file__).resolve().parent.parent / "wrapper" / "generate_single.py"
    )
    if not generate_py.exists():
        raise ValueError(f"ScrabbleGAN single-text wrapper not found: {generate_py}")
    return [
        sys.executable,
        str(generate_py),
        "--text",
        text,
        "--seed",
        str(record["seed"]),
        "--checkpoint",
        str(checkpoint_path),
        "--options-json",
        str(options_sidecar_path),
        "--output",
        str(raw_path),
        "--source-dir",
        str(source_dir),
    ]


# Input: validierter Manifest-Record und Zielpfad.
# Output: Keine Rueckgabe.
# Der Fake-Renderer ist nur fuer lokale Tests gedacht und schreibt ein kleines
# deterministisches RGBA-Bild ohne ScrabbleGAN-Abhaengigkeiten.
def _render_fake_asset(record, raw_path):
    # type: (dict, Path) -> None
    width = max(48, 8 * len(record["text"]) + 16)
    height = 32
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    x_offset = 4 + int(record["seed"]) % 5
    draw.rectangle((x_offset, 9, width - 8, 20), fill=(0, 0, 0, 255))
    image.save(raw_path)


# Input: `text` aus einem validierten Manifest-Record.
# Output: Liste einzelner Woerter fuer upstream ScrabbleGAN.
# Die Funktion haelt Leerzeichen als Batch-Tool-Komposition und schuetzt den
# Single-Word-Wrapper vor leeren Wortaufrufen.
def _split_words(text):
    # type: (str) -> list
    words = text.split(" ")
    if any(not word for word in words):
        raise ValueError(f"Text contains empty word segment: {text!r}")
    return words


# Input: rohe Word-PNGs, Zielpfad, Seed und Asset-ID.
# Output: Keine Rueckgabe.
# Die Funktion komponiert Multi-Word-Ausgaben deterministisch horizontal auf
# weissem Rohhintergrund, damit die spaetere Maskierung wie bei ScrabbleGAN greift.
def _compose_word_images(word_paths, raw_path, seed, asset_id):
    # type: (list, Path, int, str) -> None
    images = [_flatten_on_white(Image.open(path)) for path in word_paths]
    rng = random.Random(f"{seed}:{asset_id}")
    gaps = [8 + rng.randint(0, 4) for _ in range(max(0, len(images) - 1))]
    width = sum(image.size[0] for image in images) + sum(gaps)
    height = max(image.size[1] for image in images)
    canvas = Image.new("RGB", (width, height), (255, 255, 255))

    x_offset = 0
    for index, image in enumerate(images):
        y_offset = height - image.size[1]
        canvas.paste(image, (x_offset, y_offset))
        x_offset += image.size[0]
        if index < len(gaps):
            x_offset += gaps[index]
    canvas.save(raw_path)


# Input: `image` als beliebige Pillow-Ausgabe.
# Output: RGB-Bild ohne Alpha auf weissem Hintergrund.
# Die Funktion normalisiert Word-Fragmente fuer die Multi-Word-Komposition,
# ohne die eigentliche Tintenfarbe festzulegen.
def _flatten_on_white(image):
    # type: (Image.Image) -> Image.Image
    if "A" not in image.getbands():
        return image.convert("RGB")
    base = Image.new("RGBA", image.size, (255, 255, 255, 255))
    base.alpha_composite(image.convert("RGBA"))
    return base.convert("RGB")
