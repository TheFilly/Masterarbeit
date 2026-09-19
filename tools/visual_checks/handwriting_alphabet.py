"""Generate handwriting samples for manual visual inspection."""

from __future__ import annotations

from pathlib import Path

from injection_pipeline import inject_function

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
TEST_IMAGE = REPOSITORY_ROOT / "DicomData" / "images" / "blank_1600x1200.jpg"
OUTPUT_ROOT = REPOSITORY_ROOT / "output" / "handwriting-alphabet-test"

TEST_BLOCKS = (
    ("uppercase-01", "ABCDEFGHIJKLM"),
    ("uppercase-02", "NOPQRSTUVWXYZ"),
    ("lowercase-01", "abcdefghijklm"),
    ("lowercase-02", "nopqrstuvwxyz"),
    ("digits", "0123456789-"),
)


# Input: Keine Parameter.
# Output: Der feste JPG-/JPEG-Pfad fuer den manuellen visuellen Check.
# Die Funktion prueft, ob die konfigurierte Bildquelle vorhanden ist, und
# bricht mit einer klaren Meldung ab, wenn sie fehlt.
def choose_test_image() -> Path:
    if not TEST_IMAGE.is_file():
        raise FileNotFoundError(f"Test image not found: {TEST_IMAGE}.")
    return TEST_IMAGE


# Input: Bildquelle, Blockname, Testtext und deterministischer Seed.
# Output: Keine Rueckgabe; schreibt ein injiziertes Bild und Ground Truth unter
# `output/handwriting-alphabet-test/<block-name>/`.
# Der Aufruf nutzt die oeffentliche API und bleibt bewusst ausserhalb der
# automatisierten Testsuite, damit die Ausgabe manuell visuell bewertet wird.
def run_visual_check(image_path: Path, block_name: str, text: str, seed: int) -> None:
    output_dir = OUTPUT_ROOT / block_name
    injected_path, ground_truth_path = inject_function(
        category="patient_id",
        value=text,
        prefix="",
        suffix="",
        handwritten=True,
        documentType="jpg",
        input_path=image_path,
        output_dir=output_dir,
        seed=seed,
        rotation_degrees=0,
        font_size_pct=300,
        placement_mode="center",
        handwriting_ink_color="black",
        handwriting_contrast_mode="none",
    )
    print(f"{block_name}: {text}")
    print(f"  Bild: {injected_path}")
    print(f"  Ground Truth: {ground_truth_path}")


# Input: Keine Parameter.
# Output: Keine Rueckgabe; fuehrt alle manuellen visuellen Handschriftchecks aus.
# Jeder Zeichenblock bleibt unter dem Legacy-Lexikonlimit des aktuellen
# ScrabbleGAN-Wrappers und wird in einem eigenen Ausgabeordner gespeichert.
def main() -> None:
    image_path = choose_test_image()
    print(f"Verwendetes Bild: {image_path}")
    for index, (block_name, text) in enumerate(TEST_BLOCKS, start=1):
        run_visual_check(image_path, block_name, text, seed=200 + index)


if __name__ == "__main__":
    main()
