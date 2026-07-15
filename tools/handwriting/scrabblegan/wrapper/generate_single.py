"""Single-text CPU inference wrapper for the official ScrabbleGAN checkout."""

import argparse
import contextlib
import os
import random
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np
import torch
from PIL import Image


# Input: CLI-Argumente fuer einen einzelnen Text.
# Output: Keine Rueckgabe.
# Die Funktion laedt den offiziellen Amazon-Upstream aus `--source-dir`, setzt
# CPU-only Inferenz und schreibt genau ein graues PNG nach `--output`.
def main(argv=None):
    # type: (list | None) -> None
    args = _build_parser().parse_args(argv)
    source_dir = Path(args.source_dir).resolve()
    checkpoint_path = Path(args.checkpoint).resolve()
    options_path = Path(args.options_json).resolve()
    output_path = Path(args.output).resolve()

    _validate_inputs(args.text, source_dir, checkpoint_path, options_path)
    _seed_everything(args.seed)
    options = _load_options_sidecar(options_path)
    _validate_alphabet(args.text, str(options.get("alphabet", "")))
    options["inference_text"] = args.text

    sys.path.insert(0, str(source_dir))
    with _temporary_checkpoint_layout(checkpoint_path, options) as runtime_options:
        opt = _parse_upstream_options(runtime_options)
        image = _render_text(args.text, args.seed, opt)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path)


# Input: Keine Parameter.
# Output: argparse-Parser fuer den Wrapper-Vertrag.
# Die Funktion haelt den Container-Entry-Point und lokale Tests auf derselben
# stabilen Single-Text-Schnittstelle.
def _build_parser():
    # type: () -> argparse.ArgumentParser
    parser = argparse.ArgumentParser(description="Generate one ScrabbleGAN word PNG")
    parser.add_argument("--text", required=True)
    parser.add_argument("--seed", required=True, type=int)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--options-json", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--source-dir", default=".")
    return parser


# Input: Text, Source-, Checkpoint- und Optionspfad.
# Output: Keine Rueckgabe.
# Die Funktion bricht frueh mit klaren Fehlern ab, wenn lokale Voraussetzungen
# fuer die isolierte Inferenz fehlen.
def _validate_inputs(text, source_dir, checkpoint_path, options_path):
    # type: (str, Path, Path, Path) -> None
    if " " in text:
        raise ValueError(
            "generate_single.py accepts one word; batch tooling composes spaces."
        )
    if not source_dir.exists():
        raise ValueError(f"ScrabbleGAN source directory not found: {source_dir}")
    if not checkpoint_path.exists():
        raise ValueError(f"ScrabbleGAN checkpoint not found: {checkpoint_path}")
    if not options_path.exists():
        raise ValueError(f"ScrabbleGAN options sidecar not found: {options_path}")


# Input: deterministischer `seed`.
# Output: Keine Rueckgabe.
# Die Funktion setzt alle verfuegbaren Zufallsquellen fuer reproduzierbare
# CPU-Inferenz und deaktiviert CUDA fuer diesen Prozess.
def _seed_everything(seed):
    # type: (int) -> None
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if hasattr(torch, "cuda"):
        torch.cuda.manual_seed_all(seed)
    if hasattr(torch.backends, "cudnn"):
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False


# Input: `sidecar_path` als JSON oder upstream `*_opt.txt`.
# Output: Dictionary mit Optionswerten.
# Die Funktion importiert den Host-Parser absichtlich nicht, damit der Wrapper
# im alten Python-3.6-Container eigenstaendig laeuft.
def _load_options_sidecar(sidecar_path):
    # type: (Path) -> dict
    if sidecar_path.suffix.lower() == ".json":
        import json

        with sidecar_path.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
        if not isinstance(payload, dict):
            raise ValueError("Options JSON must contain an object.")
        return {str(key): value for key, value in payload.items()}

    options = {}
    with sidecar_path.open("r", encoding="utf-8") as fh:
        for raw_line in fh:
            if ":" not in raw_line:
                continue
            key, raw_value = raw_line.split(":", 1)
            value = raw_value.split("[default:", 1)[0].strip()
            if key.strip():
                options[key.strip()] = value
    return options


# Input: `text` und Alphabet aus dem Checkpoint-Sidecar.
# Output: Keine Rueckgabe.
# Die Funktion verhindert Modellaufrufe mit Zeichen, die upstream nicht
# kodieren kann.
def _validate_alphabet(text, alphabet):
    # type: (str, str) -> None
    if not alphabet:
        raise ValueError("Options sidecar does not define alphabet.")
    unsupported = [char for char in text if char not in set(alphabet)]
    if unsupported:
        unsupported_text = "".join(sorted(set(unsupported)))
        raise ValueError(
            "Text contains characters outside checkpoint alphabet: "
            f"{unsupported_text}"
        )


# Input: Checkpoint und Optionswerte.
# Output: Kontext mit temporaerem Optionsdict fuer upstream.
# Die Funktion bildet den einzelnen `latest_net_G.pth`-Checkpoint in das von
# upstream erwartete `checkpoints_dir/name/latest_net_G.pth`-Layout ab.
@contextlib.contextmanager
def _temporary_checkpoint_layout(checkpoint_path, options):
    # type: (Path, dict)
    with tempfile.TemporaryDirectory(prefix="scrabblegan-single-") as tmp_dir:
        tmp_root = Path(tmp_dir)
        experiment_name = str(options.get("name", "single_text"))
        checkpoint_dir = tmp_root / experiment_name
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(str(checkpoint_path), str(checkpoint_dir / "latest_net_G.pth"))
        for network_name in ("latest_net_D.pth", "latest_net_OCR.pth"):
            companion_path = checkpoint_path.parent / network_name
            if companion_path.exists():
                shutil.copyfile(str(companion_path), str(checkpoint_dir / network_name))
        runtime_options = dict(options)
        runtime_options["checkpoints_dir"] = str(tmp_root)
        runtime_options["name"] = experiment_name
        runtime_options["epoch"] = "latest"
        runtime_options["gpu_ids"] = "-1"
        runtime_options["batch_size"] = "1"
        runtime_options["serial_batches"] = "True"
        runtime_options["no_flip"] = "True"
        # The supplied checkpoint is the IAM/offline English model.  The
        # upstream parser defaults to RIMES, which silently selects a
        # different alphabet and therefore a different generator shape.
        runtime_options["dataname"] = "IAMcharH32W16rmPunct"
        # The official model initializes its fixed noise and label tensors from
        # a lexicon even during inference.  Single-text inference does not need
        # the training lexicon, so provide a minimal runtime lexicon containing
        # the requested word instead of requiring the optional dataset tree.
        lexicon_path = tmp_root / "single_text_lexicon.txt"
        lexicon_path.write_text(
            str(options.get("inference_text", "")) + "\n", encoding="utf-8"
        )
        runtime_options["lex"] = str(lexicon_path)
        yield runtime_options


# Input: Runtime-Optionen fuer den offiziellen `TestOptions`-Parser.
# Output: upstream Options-Namespace.
# Die Funktion parst upstream mit CPU-Flags und monkeypatcht `torch.load`, damit
# GPU-trainierte Checkpoints auf CPU geladen werden koennen.
def _parse_upstream_options(options):
    # type: (dict) -> object
    from options.test_options import TestOptions

    argv = ["generate_single.py"]
    selected_options = _selected_upstream_options(options)
    if selected_options.get("model") == "CharInterGAN":
        # The supplied checkpoint sidecar uses the historical experiment name;
        # this Amazon checkout exposes the compatible implementation as
        # `ScrabbleGAN_model.py`.
        selected_options["model"] = "ScrabbleGAN"
    for key, value in selected_options.items():
        if str(value).lower() == "false":
            continue
        flag = f"--{key}"
        if str(value).lower() == "true":
            argv.append(flag)
        else:
            argv.extend([flag, str(value)])

    old_argv = sys.argv
    sys.argv = argv
    try:
        opt = TestOptions().parse()
    finally:
        sys.argv = old_argv
    opt.gpu_ids = []
    opt.isTrain = False
    return opt


# Input: Vollstaendige Runtime-Optionen.
# Output: Gefiltertes Dictionary fuer upstream argparse.
# Die Funktion vermeidet unbekannte Zusatzfelder aus JSON-Sidecars und reicht
# nur modellrelevante Optionen weiter.
def _selected_upstream_options(options):
    # type: (dict) -> dict
    keys = (
        "alphabet",
        "batch_size",
        "bg_color",
        "bottom_height",
        "bottom_width",
        "capitalize",
        "checkpoints_dir",
        "dataname",
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
        "gpu_ids",
        "height",
        "height_char",
        "hier",
        "imgH",
        "input_nc",
        "len_vocab",
        "lex",
        "max_width",
        "model",
        "name",
        "no_concat_dataset",
        "no_flip",
        "norm_style",
        "num_layers",
        "num_layers_OCR",
        "one_hot",
        "output_nc",
        "padding",
        "serial_batches",
        "style_dim",
        "use_rnn",
        "where_add",
        "which_linear",
    )
    return {key: options[key] for key in keys if key in options}


# Input: Einzelnes Wort, Seed und upstream Options-Namespace.
# Output: Pillow-L-Bild mit generierter Handschrift.
# Die Funktion nutzt die offizielle `create_model`-Factory und ruft denselben
# `model.forward(words, z)`-Pfad wie upstream `generate_wordsLMDB.py` auf.
def _render_text(text, seed, opt):
    # type: (str, int, object) -> Image.Image
    from models import create_model
    from util.util import prepare_z_y

    _patch_torch_load_for_cpu()
    model = create_model(opt)
    model.setup(opt)
    model.eval()

    z, _ = prepare_z_y(
        1,
        opt.dim_z,
        max(1, len(getattr(model, "lex", []))),
        device="cpu",
        fp16=False,
        seed=seed,
    )
    model.device = "cpu"
    model.forward([text.encode("utf-8")], z)
    array = model.fake.data.cpu().numpy().squeeze(0).squeeze(0)
    array = ((array + 1.0) * 127.5).clip(0, 255).astype(np.uint8)
    return Image.fromarray(array, mode="L")


# Input: Keine Parameter.
# Output: Keine Rueckgabe.
# Die Funktion ersetzt `torch.load` pro Prozess durch eine CPU-map_location-
# Variante, damit CUDA-Checkpoints im CPU-Container geladen werden.
def _patch_torch_load_for_cpu():
    # type: () -> None
    original_load = torch.load

    def _cpu_load(*args, **kwargs):
        # type: (*object, **object) -> object
        kwargs.setdefault("map_location", "cpu")
        return original_load(*args, **kwargs)

    torch.load = _cpu_load


if __name__ == "__main__":
    main()
