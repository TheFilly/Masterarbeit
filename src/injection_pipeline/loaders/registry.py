"""Deterministic adapter registry for document loaders and writers."""

from pathlib import Path

from injection_pipeline.models.adapters import DocumentLoader, DocumentWriter

_ADAPTERS_BY_EXTENSION: dict[str, tuple[DocumentLoader, DocumentWriter]] = {}
_REGISTERED_EXTENSIONS: list[str] = []


# Input: `loader` und `writer` fuer denselben Format-Identifier.
# Output: Keine Rueckgabe.
# Die Funktion registriert jede Erweiterung deterministisch und lehnt
# widerspruechliche Adapterpaare ab.
def register(loader: DocumentLoader, writer: DocumentWriter) -> None:
    if loader.format_id != writer.format_id:
        raise ValueError(
            "Loader and writer format_id must match: "
            f"{loader.format_id!r} != {writer.format_id!r}."
        )
    for extension in loader.extensions:
        normalized_extension = _normalize_extension(extension)
        existing_pair = _ADAPTERS_BY_EXTENSION.get(normalized_extension)
        new_pair = (loader, writer)
        if existing_pair is not None and existing_pair != new_pair:
            raise ValueError(f"Adapter already registered for {normalized_extension}.")
        if existing_pair is None:
            _ADAPTERS_BY_EXTENSION[normalized_extension] = new_pair
            _REGISTERED_EXTENSIONS.append(normalized_extension)


# Input: `path` mit Eingabedatei.
# Output: Loader/Writer-Paar fuer die Dateiendung.
# Die Funktion ist der einzige Format-Dispatch fuer den Runner und meldet
# unbekannte Formate mit dem bisherigen ValueError-Text.
def resolve(path: Path) -> tuple[DocumentLoader, DocumentWriter]:
    suffix = path.suffix.lower()
    adapter_pair = _ADAPTERS_BY_EXTENSION.get(suffix)
    if adapter_pair is None:
        raise ValueError(
            f"Unsupported input format. Expected {_format_expected_extensions()}."
        )
    return adapter_pair


# Input: Keine Eingabe.
# Output: Registrierte Erweiterungen in expliziter Registrierungsreihenfolge.
# Die Funktion dient Tests und Fehlermeldungen, ohne die interne Registry
# mutierbar offenzulegen.
def registered_extensions() -> tuple[str, ...]:
    return tuple(_REGISTERED_EXTENSIONS)


# Input: `extension` mit oder ohne fuehrendem Punkt.
# Output: Normalisierte Kleinschreibungs-Erweiterung.
# Die Funktion haelt Registrierung und Aufloesung robust gegen Schreibvarianten.
def _normalize_extension(extension: str) -> str:
    normalized = extension.lower()
    if not normalized.startswith("."):
        normalized = f".{normalized}"
    return normalized


# Input: Keine Eingabe.
# Output: Menschenlesbare Erweiterungsliste fuer ValueError-Meldungen.
# Die Funktion bewahrt den bisherigen Text fuer drei Formate exakt.
def _format_expected_extensions() -> str:
    extensions = registered_extensions()
    if len(extensions) == 1:
        return extensions[0]
    return f"{', '.join(extensions[:-1])}, or {extensions[-1]}"


# Input: Keine Eingabe.
# Output: Keine Rueckgabe.
# Die Funktion importiert Adapter erst nach Registry-Initialisierung und legt
# die Standardreihenfolge DICOM, JPG fest.
def _register_default_adapters() -> None:
    from injection_pipeline.loaders.dicom import DicomLoader
    from injection_pipeline.loaders.jpg import JpgLoader
    from injection_pipeline.writers.dicom import DicomWriter
    from injection_pipeline.writers.jpg import JpgWriter

    register(DicomLoader(), DicomWriter())
    register(JpgLoader(), JpgWriter())


_register_default_adapters()
