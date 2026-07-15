"""Options-sidecar helpers for isolated ScrabbleGAN runs."""

import json

_DEFAULT_SIDECAR_NAMES = (
    "options.json",
    "test_opt.json",
    "train_opt.json",
    "test_opt.txt",
    "train_opt.txt",
)


# Input: `checkpoint_path` und optionaler expliziter `sidecar_path`.
# Output: Pfad zum Options-Sidecar oder `None`.
# Die Funktion findet die zu `latest_net_G.pth` gehoerenden Optionen im
# Checkpoint-Ordner, ohne Checkpoints oder externe Daten zu veraendern.
def resolve_options_sidecar(checkpoint_path, sidecar_path=None):
    # type: (Path, Path | None) -> Path | None
    if sidecar_path is not None:
        if not sidecar_path.exists():
            raise ValueError(f"Options sidecar not found: {sidecar_path}")
        return sidecar_path

    checkpoint_dir = checkpoint_path.parent
    for name in _DEFAULT_SIDECAR_NAMES:
        candidate = checkpoint_dir / name
        if candidate.exists():
            return candidate
    return None


# Input: `sidecar_path` als JSON-Datei oder upstream `*_opt.txt`.
# Output: Dictionary mit stringbasierten ScrabbleGAN-Optionen.
# Die Funktion unterstuetzt sowohl ein sauberes JSON-Sidecar als auch die von
# upstream gespeicherten `test_opt.txt`/`train_opt.txt`-Dateien.
def load_options_sidecar(sidecar_path):
    # type: (Path) -> dict
    if sidecar_path.suffix.lower() == ".json":
        with sidecar_path.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
        if not isinstance(payload, dict):
            raise ValueError(
                f"Options sidecar must contain a JSON object: {sidecar_path}"
            )
        return {str(key): value for key, value in payload.items()}

    return _load_upstream_opt_txt(sidecar_path)


# Input: geladene `options` aus einem Sidecar.
# Output: Alphabet-String oder `None`.
# Die Funktion extrahiert die Modellalphabet-Option fuer Manifestvalidierung
# und Wrapper-Aufrufe.
def extract_alphabet(options):
    # type: (dict | None) -> str | None
    if not options:
        return None
    alphabet = options.get("alphabet")
    if alphabet is None:
        return None
    alphabet = str(alphabet)
    if not alphabet:
        return None
    return alphabet


# Input: geladene `options` aus JSON oder upstream Text.
# Output: Argumentliste fuer upstream `TestOptions`.
# Die Funktion gibt nur Optionen weiter, die fuer CPU-Inferenz und
# Generator-Rekonstruktion relevant sind.
def build_upstream_argv(options):
    # type: (dict) -> list
    selected_keys = (
        "alphabet",
        "batch_size",
        "bg_color",
        "bottom_height",
        "bottom_width",
        "capitalize",
        "crop_size",
        "dataset_mode",
        "dim_z",
        "embedding_size",
        "epoch",
        "first_layer",
        "G_ch",
        "G_depth",
        "G_nl",
        "G_param",
        "height",
        "height_char",
        "hier",
        "imgH",
        "input_nc",
        "len_vocab",
        "max_width",
        "model",
        "name",
        "no_concat_dataset",
        "no_flip",
        "norm_style",
        "num_layers",
        "one_hot",
        "output_nc",
        "padding",
        "style_dim",
        "use_rnn",
        "where_add",
        "which_linear",
    )
    argv = []
    for key in selected_keys:
        if key not in options:
            continue
        value = options[key]
        if _is_false(value):
            continue
        flag = f"--{key}"
        if _is_true(value):
            argv.append(flag)
        else:
            argv.extend([flag, str(value)])
    return argv


# Input: upstream `*_opt.txt`-Datei.
# Output: Dictionary mit Optionsnamen und bereinigten Werten.
# Die Funktion parst die menschenlesbare Optionsdatei, die upstream neben
# Checkpoints speichert.
def _load_upstream_opt_txt(sidecar_path):
    # type: (Path) -> dict
    options = {}
    with sidecar_path.open("r", encoding="utf-8") as fh:
        for raw_line in fh:
            if ":" not in raw_line:
                continue
            key, raw_value = raw_line.split(":", 1)
            key = key.strip()
            if not key:
                continue
            value = raw_value.split("[default:", 1)[0].strip()
            options[key] = value
    if not options:
        raise ValueError(
            f"Options sidecar contains no parseable options: {sidecar_path}"
        )
    return options


# Input: beliebiger Optionswert.
# Output: `True`, wenn der Wert eine aktivierte Boolean-Option darstellt.
# Die Funktion haelt die JSON- und upstream-Textdarstellung kompatibel.
def _is_true(value):
    # type: (object) -> bool
    return value is True or str(value).lower() == "true"


# Input: beliebiger Optionswert.
# Output: `True`, wenn der Wert eine deaktivierte Boolean-Option darstellt.
# Die Funktion verhindert, dass False-Werte als String-Argumente an upstream
# weitergereicht werden.
def _is_false(value):
    # type: (object) -> bool
    return value is False or str(value).lower() == "false"
