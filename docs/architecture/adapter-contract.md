# Format-Adapter-Vertrag (WP-F)

Status: für DICOM/JPG und den dedizierten PDF-Workflow implementiert, aktualisiert
2026-07-14. ADR-0006 definiert eine Loader-/Writer-Schnittstelle pro
Injektionsmodalität.

## Vertrag

```python
class DocumentLoader(Protocol):
    format_id: ClassVar[str]
    extensions: ClassVar[tuple[str, ...]]

    def load(self, path: Path) -> SourceDocument: ...


class DocumentWriter(Protocol):
    format_id: ClassVar[str]
    output_suffix: ClassVar[str]

    def write(self, document: InjectedDocument, output_path: Path) -> None: ...
```

`SourceDocument` und `InjectedDocument` sind die typisierten
Schnittstellenmodelle in `models/adapters.py`. DICOM und JPG verwenden den
Vertrag direkt. Ihre Registry-Einträge werden über die Quellendung aufgelöst;
der Runner enthält keine formatspezifischen Load-/Save-Zweige.

## PDF-Modalität

PDF ist eine eigenständige Eingabemodalität und kein Composer nach dem Run. Die PDF-Operation
akzeptiert ein PDF-Eingabe-Template, ein bereits injiziertes DICOM und die
JSON-Annotation dieses DICOM-Runs. Der PDF-Loader validiert Eingabe-PDF und
Seitengometrie. Der bestehende DICOM-Loader liest den injizierten Frame, der
kanonische Run-Record-Loader validiert die Annotation. Der PDF-Writer platziert
die zugehörige Preview auf der ausgewählten Seite, bildet Bildraum-Quads auf
PDF-Raum-Quads ab, führt eine neue Ebene mit einer Kopie der Eingabe-PDF
zusammen und schreibt den PDF-Sidecar.

PDF-spezifische Request-/Response-Modelle liegen in
`injection_pipeline/pdf/`. Sie besitzen Seiten-, Slot-, Platzierungs- und
Sidecar-Felder; die gemeinsamen Modelle `ImagePoint`, `PdfPoint` und `Quad`
bleiben in `models/geometry.py`. Die PDF-Implementierung darf dem DICOM/JPG-
Injektions-Engine keine PDF-Zweige hinzufügen.

Konkrete Einstiegspunkte sind `PdfLoader.load(path)` und
`PdfWriterAdapter.write(template, dicom_path, annotation_path, output_root,
slot, page_index)`. Der Writer gibt typisierte PDF-Ausgabe-Artefakte zurück.

| Aspekt | DICOM | JPG | PDF |
|---|---|---|---|
| Loader | pydicom-Dataset und Frame | Pillow-RGB-Bild | PDF-Seiten und Seitengeometrie |
| Metadaten-Injektion | DICOM-Tag-Plan | keine | keine |
| Schreiben | DICOM-Pixelarray und Tags | JPEG-Pixel | reportlab-Overlay, über pypdf mit Input zusammengeführt |
| Ausgabe | `.dcm` | `.jpg` | `.pdf` plus JSON-Sidecar |

Die PDF-Quelldateien werden nie verändert. Die Ausgabe wird unter
`output/pdf/<run_id>/<template-stem>-<slot>/` abgelegt, damit der Quell-Run von
DICOM für den DICOM/JPG-Reproduzierbarkeitstest byteidentisch bleibt.
Der Writer weist Aliase zwischen diesen Quellen und jedem erzeugten Ausgabe-
pfad zurück, bevor das Ausgabeverzeichnis angelegt wird.

Die öffentliche `make_pdf`-API behält dieselbe Adaptergrenze bei, setzt aber
mehrere bereits injizierte Bilder sowie mehrere Textspezifikationen in ein PDF.
Sie verwendet PDF-Loader/Writer und gemeinsame Geometrie, wo dies sinnvoll ist,
besitzt aber eigene Kompositionsmodelle für die Platzierung mehrerer Elemente,
die geseedete Bildrotation, das Anhängen von Seiten und ein
`PdfMakeArtifacts`-Rückgabeobjekt mit erzeugtem PDF, annotiertem PDF, Sidecar
und Layout-Metadaten.

## PDF-Implementierungsübergabe

Der freigegebene Umfang und die Tests werden in
`docs/pdf-template-injection-plan.md` gepflegt. Die Implementierung ergänzt
`reportlab` und `pypdf`, stellt ein PDF-Loader/Writer-Paar bereit und bietet eine
CLI-Operation, die `--input-pdf`, `--input-dicom` und `--dicom-annotation`
benötigt (sowie optional `--output-dir`, `--slot` und `--page-index`). Alle
Eingabe-PDF-Seiten sowie die Reihenfolge der Quell-Annotationen und -Ecken
müssen erhalten bleiben.

## Implementierungsstatus

Für DICOM/JPG implementiert:

- Adaptermodelle, Protokolle und Erweiterungsregistry;
- DICOM-Loader/Writer mit Tagänderung und Pixelspeicherung;
- JPG-Loader/Writer mit RGB-Konvertierung und JPEG-Speicherung; sowie
- Runner-Auflösung und Unit-/Integrationsabdeckung.

PDF-Loader/Writer, Sidecar-Modelle und CLI sind implementiert. Eine breitere
Abdeckung mit operativen Fixtures bleibt offen. Ihre Schema-Version ist
`0.3.0-pdf-prototype` gemäß ADR-0008.
