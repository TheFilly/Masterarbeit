"""Stable seed derivation for named pipeline streams."""

import hashlib


# Input: `seed` als Run-Seed und `stream_name` als benannter Zufallsstrom.
# Output: Plattformstabiler Integer-Seed aus SHA-256.
# Die Funktion nutzt die ersten acht Digest-Bytes und vermeidet Pythons
# prozessgesalzenes `hash()` fuer reproduzierbare Ableitungen.
def derive_seed(seed: int, stream_name: str) -> int:
    digest = hashlib.sha256(f"{seed}:{stream_name}".encode()).digest()
    return int.from_bytes(digest[:8], "big")
