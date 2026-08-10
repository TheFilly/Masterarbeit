"""Public runner and CLI option defaults."""

from pathlib import Path

DEFAULT_OUTPUT_DIR = Path("output")
HANDWRITING_FONT_FAMILY = "handwriting"
FONT_FAMILY_CHOICES: tuple[str, ...] = (
    "arial",
    "calibri",
    "tahoma",
    "consolas",
    HANDWRITING_FONT_FAMILY,
)
TEXT_BACKGROUND_CHOICES: tuple[str, ...] = ("white",)
HANDWRITING_INK_COLOR_CHOICES: tuple[str, ...] = (
    "auto",
    "black",
    "gray",
    "white",
)
HANDWRITING_CONTRAST_MODE_CHOICES: tuple[str, ...] = ("none", "halo")
SHOW_LABEL_BOX_CHOICES: tuple[str, ...] = ("y", "n")
DEFAULT_HANDWRITING_ASSET_ROOT = Path("DicomData") / "HandwritingAssets"
DEFAULT_HANDWRITING_CHECKPOINT_PATH = (
    DEFAULT_HANDWRITING_ASSET_ROOT / "scrabblegan" / "checkpoints" / "latest_net_G.pth"
)
DEFAULT_HANDWRITING_SOURCE_DIR = (
    DEFAULT_HANDWRITING_ASSET_ROOT / "scrabblegan" / "source"
)
DEFAULT_HANDWRITING_CONTAINER_IMAGE = "injection-scrabblegan"
