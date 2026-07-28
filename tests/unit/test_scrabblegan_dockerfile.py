"""Regression checks for the isolated ScrabbleGAN Docker runtime."""

from pathlib import Path


def test_scrabblegan_dockerfile_pins_legacy_amd64_platform() -> None:
    dockerfile = Path("tools/handwriting/scrabblegan/Dockerfile")

    content = dockerfile.read_text(encoding="utf-8")

    assert "ARG SCRABBLEGAN_IMAGE_PLATFORM=linux/amd64" in content
    assert (
        "FROM --platform=${SCRABBLEGAN_IMAGE_PLATFORM} mambaorg/micromamba"
        in content
    )
