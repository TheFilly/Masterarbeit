"""Deterministic seed derivation tests."""

from injection_pipeline.runtime.seeding import derive_seed


def test_derive_seed_uses_stable_sha256_streams() -> None:
    assert derive_seed(42, "input_selection") == 687305538156123501
    assert derive_seed(42, "identity_b") == 15792787834403702054
    assert derive_seed(42, "placement") == 3662267196294883271


def test_derive_seed_separates_stream_names() -> None:
    assert derive_seed(42, "identity_b") != derive_seed(42, "input_selection")
    assert derive_seed(42, "identity_b") != derive_seed(43, "identity_b")
