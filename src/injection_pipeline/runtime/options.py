"""Public runner and CLI option defaults."""

from pathlib import Path

DEFAULT_OUTPUT_DIR = Path("output")
FONT_FAMILY_CHOICES: tuple[str, ...] = ("arial", "calibri", "tahoma", "consolas")
TEXT_BACKGROUND_CHOICES: tuple[str, ...] = ("white",)
SHOW_LABEL_BOX_CHOICES: tuple[str, ...] = ("y", "n")
