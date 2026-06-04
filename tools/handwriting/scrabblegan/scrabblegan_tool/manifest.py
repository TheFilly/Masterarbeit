"""JSONL manifest parsing and validation for ScrabbleGAN batch runs."""

import json

ALLOWED_FIELDS = ("patient_name", "patient_id", "accession_number")
ALLOWED_INK_COLORS = ("black", "gray", "white")
ALLOWED_BACKGROUNDS = ("transparent", "white")

_REQUIRED_INPUT_KEYS = (
    "asset_id",
    "field",
    "text",
    "ink_color",
    "background",
    "seed",
)


# Input: `manifest_path` mit einem JSONL-Batch-Manifest.
# Output: Liste normalisierter Input-Records.
# Die Funktion validiert den v1-Vertrag hart und meldet Zeilennummern fuer
# fehlerhafte Records.
def load_input_manifest(manifest_path):
    # type: (Path) -> list
    if not manifest_path.exists():
        raise ValueError(f"Input manifest not found: {manifest_path}")

    records = []
    seen_asset_ids = set()
    with manifest_path.open("r", encoding="utf-8") as fh:
        for line_number, raw_line in enumerate(fh, start=1):
            if not raw_line.strip():
                continue
            try:
                payload = json.loads(raw_line)
            except ValueError as exc:
                raise ValueError(
                    f"Invalid JSON on line {line_number}: {exc}"
                ) from exc
            record = _validate_input_record(payload, line_number)
            asset_id = record["asset_id"]
            if asset_id in seen_asset_ids:
                raise ValueError(
                    f"Duplicate asset_id on line {line_number}: {asset_id}"
                )
            seen_asset_ids.add(asset_id)
            records.append(record)

    if not records:
        raise ValueError("Input manifest contains no asset records.")
    return records


# Input: `payload` aus JSON und `line_number` fuer Fehlertexte.
# Output: Normalisierter Input-Record.
# Die Funktion kapselt die Feld-, Options- und Typvalidierung fuer einen
# einzelnen v1-Batch-Eintrag.
def _validate_input_record(payload, line_number):
    # type: (dict, int) -> dict
    if not isinstance(payload, dict):
        raise ValueError(f"Line {line_number} must contain a JSON object.")
    for key in _REQUIRED_INPUT_KEYS:
        if key not in payload:
            raise ValueError(f"Line {line_number} missing required key: {key}")

    asset_id = str(payload["asset_id"]).strip()
    field = str(payload["field"]).strip()
    text = str(payload["text"])
    ink_color = str(payload["ink_color"]).strip()
    background = str(payload["background"]).strip()

    if not asset_id:
        raise ValueError(f"Line {line_number} has empty asset_id.")
    if field not in ALLOWED_FIELDS:
        raise ValueError(f"Line {line_number} has unsupported field: {field}")
    if not text:
        raise ValueError(f"Line {line_number} has empty text.")
    if ink_color not in ALLOWED_INK_COLORS:
        raise ValueError(f"Line {line_number} has unsupported ink_color: {ink_color}")
    if background not in ALLOWED_BACKGROUNDS:
        raise ValueError(f"Line {line_number} has unsupported background: {background}")
    try:
        seed = int(payload["seed"])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Line {line_number} seed must be an integer.") from exc

    return {
        "asset_id": asset_id,
        "field": field,
        "text": text,
        "ink_color": ink_color,
        "background": background,
        "seed": seed,
    }


# Input: `manifest_path` mit einem Generator-Output-Manifest.
# Output: Liste der JSONL-Records.
# Die Funktion laedt nur Objekte und laesst die semantische Pruefung dem
# Validator-Modul.
def load_output_manifest(manifest_path):
    # type: (Path) -> list
    if not manifest_path.exists():
        raise ValueError(f"Output manifest not found: {manifest_path}")

    records = []
    with manifest_path.open("r", encoding="utf-8") as fh:
        for line_number, raw_line in enumerate(fh, start=1):
            if not raw_line.strip():
                continue
            try:
                payload = json.loads(raw_line)
            except ValueError as exc:
                raise ValueError(
                    f"Invalid JSON on line {line_number}: {exc}"
                ) from exc
            if not isinstance(payload, dict):
                raise ValueError(f"Line {line_number} must contain a JSON object.")
            records.append(payload)

    if not records:
        raise ValueError("Output manifest contains no asset records.")
    return records


# Input: `records` und Ziel-`manifest_path`.
# Output: Keine Rueckgabe.
# Die Funktion schreibt ein JSONL-Manifest mit stabil sortierten Keys und legt
# den Zielordner bei Bedarf an.
def write_output_manifest(records, manifest_path):
    # type: (list, Path) -> None
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, sort_keys=True))
            fh.write("\n")
