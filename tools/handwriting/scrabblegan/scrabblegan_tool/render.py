"""Rendering adapter around a mounted ScrabbleGAN checkout."""

import shlex
import subprocess
import sys

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
        commit = commit_file.read_text(encoding="utf-8").strip()
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
    generator_command=None,
    fake_renderer=False,
):
    # type: (dict, Path, Path, Path, str, bool) -> None
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    if fake_renderer:
        _render_fake_asset(record, raw_path)
        return

    command = _build_generator_command(
        record, raw_path, source_dir, checkpoint_path, generator_command
    )
    subprocess.check_call(command, cwd=str(source_dir))
    if not raw_path.exists():
        raise ValueError(f"ScrabbleGAN command did not write raw output: {raw_path}")


# Input: Render-Record, Zielpfad, Source, Checkpoint und optionale Template.
# Output: Argumentliste fuer `subprocess`.
# Die Funktion bietet einen konservativen Default fuer `generate.py`, erlaubt
# aber projektspezifische Upstream-Wrapper ueber Platzhalter.
def _build_generator_command(
    record, raw_path, source_dir, checkpoint_path, generator_command
):
    # type: (dict, Path, Path, Path, str) -> list
    placeholders = {
        "text": record["text"],
        "seed": str(record["seed"]),
        "output": str(raw_path),
        "source_dir": str(source_dir),
        "checkpoint": str(checkpoint_path),
        "asset_id": record["asset_id"],
        "field": record["field"],
    }
    if generator_command:
        return [part.format(**placeholders) for part in shlex.split(generator_command)]

    generate_py = source_dir / "generate.py"
    if not generate_py.exists():
        raise ValueError(
            "No generator command supplied and generate.py was not found in "
            f"{source_dir}."
        )
    return [
        sys.executable,
        str(generate_py),
        "--text",
        record["text"],
        "--seed",
        str(record["seed"]),
        "--checkpoint",
        str(checkpoint_path),
        "--output",
        str(raw_path),
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
