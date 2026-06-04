"""Hash helpers for generated handwriting assets."""

import hashlib


# Input: `path` mit einer lokalen Datei.
# Output: Hex-codierter SHA-256-Hash.
# Die Funktion streamt die Datei, damit auch groessere Checkpoints ohne
# vollstaendiges Laden in den Speicher validiert werden koennen.
def sha256_file(path):
    # type: (Path) -> str
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


# Input: `path` und erwarteter `expected_sha256`.
# Output: Keine Rueckgabe.
# Die Funktion bricht mit ValueError ab, wenn Datei fehlt oder der Hash nicht
# exakt dem erwarteten Wert entspricht.
def require_sha256(path, expected_sha256):
    # type: (Path, str) -> None
    if not path.exists():
        raise ValueError(f"Missing file for SHA-256 validation: {path}")
    actual_sha256 = sha256_file(path)
    if actual_sha256 != expected_sha256:
        raise ValueError(
            f"SHA-256 mismatch for {path}: expected {expected_sha256}, "
            f"got {actual_sha256}"
        )
