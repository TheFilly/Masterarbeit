"""Smoke test — verifies the package is importable."""

import injection_pipeline


def test_package_importable() -> None:
    """The top-level package must be importable without errors."""
    assert injection_pipeline is not None
