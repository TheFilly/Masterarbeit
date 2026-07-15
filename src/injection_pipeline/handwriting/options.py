"""ScrabbleGAN options-sidecar loading for integrated handwriting runs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_DEFAULT_SIDECAR_NAMES: tuple[str, ...] = (
    "options.json",
    "test_opt.json",
    "train_opt.json",
    "test_opt.txt",
    "train_opt.txt",
)


# Input: `checkpoint_path` und optionaler expliziter Sidecar-Pfad.
# Output: Gefundener Sidecar-Pfad.
# Die Funktion bildet denselben Checkpoint-nahen Vertrag wie das Batch-Tool ab
# und meldet fehlende Optionen hart, damit kein Default-Alphabet genutzt wird.
def resolve_options_sidecar(
    checkpoint_path: Path,
    explicit_sidecar_path: Path | None = None,
) -> Path:
    if explicit_sidecar_path is not None:
        if not explicit_sidecar_path.exists():
            raise ValueError(
                f"Handwriting options sidecar not found: {explicit_sidecar_path}"
            )
        return explicit_sidecar_path

    for name in _DEFAULT_SIDECAR_NAMES:
        candidate = checkpoint_path.parent / name
        if candidate.exists():
            return candidate
    raise ValueError(
        "Handwriting generation requires --handwriting-options-json or an "
        "options/test_opt/train_opt sidecar next to the checkpoint."
    )


# Input: `sidecar_path` als JSON-Datei oder upstream `*_opt.txt`.
# Output: Dictionary mit ScrabbleGAN-Optionswerten.
# Die Funktion unterstuetzt den integrierten Provider ohne Abhaengigkeit vom
# isolierten Tool-Modul und laesst unparsebare Dateien hart fehlschlagen.
def load_options_sidecar(sidecar_path: Path) -> dict[str, Any]:
    if sidecar_path.suffix.lower() == ".json":
        with sidecar_path.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
        if not isinstance(payload, dict):
            raise ValueError(
                f"Handwriting options sidecar must contain an object: {sidecar_path}"
            )
        return {str(key): value for key, value in payload.items()}
    return _load_upstream_opt_txt(sidecar_path)


# Input: `options` aus einem Sidecar.
# Output: Nichtleeres Alphabet.
# Die Funktion verhindert Provider-Laeufe ohne Checkpoint-Alphabet, da dieses
# Alphabet Teil von Validierung und Cache-Identitaet ist.
def extract_required_alphabet(options: dict[str, Any]) -> str:
    alphabet = str(options.get("alphabet", ""))
    if alphabet == "":
        raise ValueError("Handwriting options sidecar must define alphabet.")
    return alphabet


# Input: upstream `test_opt.txt` oder `train_opt.txt`.
# Output: Dictionary mit Optionswerten.
# Die Funktion liest das menschenlesbare upstream-Format und entfernt die
# `[default: ...]`-Annotationen aus den gespeicherten Werten.
def _load_upstream_opt_txt(sidecar_path: Path) -> dict[str, str]:
    options: dict[str, str] = {}
    with sidecar_path.open("r", encoding="utf-8") as fh:
        for raw_line in fh:
            if ":" not in raw_line:
                continue
            key, raw_value = raw_line.split(":", 1)
            key = key.strip()
            if key == "":
                continue
            options[key] = raw_value.split("[default:", 1)[0].strip()
    if not options:
        raise ValueError(
            f"Handwriting options sidecar contains no parseable options: {sidecar_path}"
        )
    return options
