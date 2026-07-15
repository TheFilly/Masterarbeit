"""JSONL and JSON manifest parsing for ScrabbleGAN batch runs."""

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
# fehlerhafte Records. Wenn ein Alphabet uebergeben wird, werden Leerzeichen
# nur als Worttrenner erlaubt und alle anderen Zeichen gegen das Modell geprueft.
def load_input_manifest(manifest_path, alphabet=None):
    # type: (Path, str | None) -> list
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
            record = _validate_input_record(payload, line_number, alphabet)
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
def _validate_input_record(payload, line_number, alphabet):
    # type: (dict, int, str | None) -> dict
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
    if text != text.strip() or "\t" in text or "\n" in text or "\r" in text:
        raise ValueError(f"Line {line_number} has invalid text whitespace.")
    if alphabet is not None:
        _validate_text_alphabet(text, alphabet, line_number)
    if ink_color not in ALLOWED_INK_COLORS:
        raise ValueError(f"Line {line_number} has unsupported ink_color: {ink_color}")
    if background not in ALLOWED_BACKGROUNDS:
        raise ValueError(f"Line {line_number} has unsupported background: {background}")
    if ink_color == "white" and background == "white":
        raise ValueError(f"Line {line_number} has invisible white-on-white rendering.")
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


# Input: `text`, Modell-`alphabet` und `line_number` fuer Fehlertexte.
# Output: Keine Rueckgabe.
# Die Funktion erlaubt Leerzeichen als Multi-Word-Trenner, lehnt aber jedes
# Zeichen ab, das der ScrabbleGAN-Checkpoint nicht kodieren kann.
def _validate_text_alphabet(text, alphabet, line_number):
    # type: (str, str, int) -> None
    allowed = set(alphabet)
    for char in text:
        if char == " ":
            continue
        if char not in allowed:
            raise ValueError(
                f"Line {line_number} contains character outside "
                f"checkpoint alphabet: {char!r}"
            )


# Input: `manifest_path` mit einem Generator-Output-Manifest.
# Output: Liste der JSONL-Records.
# Die Funktion laedt nur Objekte und laesst die semantische Pruefung dem
# Validator-Modul.
def load_output_manifest(manifest_path):
    # type: (Path) -> list
    if not manifest_path.exists():
        raise ValueError(f"Output manifest not found: {manifest_path}")

    raw_manifest = manifest_path.read_text(encoding="utf-8")
    records = _load_json_manifest(raw_manifest)

    if not records:
        raise ValueError("Output manifest contains no asset records.")
    return records


# Input: Vollstaendiger Manifest-Text.
# Output: Liste von Output-Records aus JSON oder JSONL.
# Die Funktion akzeptiert sowohl das Pipeline-Manifest mit `assets` als auch
# das zeilenbasierte Batch-Format des isolierten ScrabbleGAN-Tools.
def _load_json_manifest(raw_manifest):
    # type: (str) -> list
    try:
        payload = json.loads(raw_manifest)
    except ValueError:
        records = []
        for line_number, raw_line in enumerate(raw_manifest.splitlines(), start=1):
            if not raw_line.strip():
                continue
            try:
                line_payload = json.loads(raw_line)
            except ValueError as exc:
                raise ValueError(
                    f"Invalid JSON on line {line_number}: {exc}"
                ) from exc
            if not isinstance(line_payload, dict):
                raise ValueError(
                    f"Line {line_number} must contain a JSON object."
                ) from None
            records.append(line_payload)
        return records

    if isinstance(payload, dict) and isinstance(payload.get("assets"), list):
        records = payload["assets"]
    elif isinstance(payload, dict):
        records = [payload]
    elif isinstance(payload, list):
        records = payload
    else:
        raise ValueError("JSON output manifest must contain an assets list.")

    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            raise ValueError(f"JSON asset {index} must contain an object.")
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
