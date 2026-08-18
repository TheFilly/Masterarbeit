# Implementierungsplan für PDF-Template-Injektion

Status: **implementiert** (2026-07-14). PDF ist eine eigenständige
Injektionsmodalität. Wie DICOM und JPG besitzt sie einen eigenen Loader und
Writer und ist kein Composer nach dem Run.

Implementiert sind der CLI-Workflow `inject-pdf`/`compose-pdf` und die
öffentliche Python-Kompositions-API `make_pdf`. `make_pdf` erweitert die
Komposition auf mehrere bereits injizierte Bilder und mehrere PDF-Texteinträge
in einer Ausgabe-PDF.

## Zweck und Eingabevertrag

Der PDF-Pfad kombiniert drei Eingaben:

1. ein vorhandenes PDF-Template (`--input-pdf`),
2. ein bereits injiziertes DICOM (`--input-dicom`) und
3. die JSON-Ground-Truth-Annotation des DICOM-Runs (`--dicom-annotation`).

Der PDF-Loader validiert das Template und stellt seine Seitengröße bereit. Der
DICOM-Loader liest den injizierten Pixel-Frame, und der Annotation-Loader
validiert den zugehörigen `RunRecord`. Der PDF-Writer platziert die zum
injizierten DICOM gehörende Preview auf der ausgewählten Template-Seite,
transformiert Bildraum-Annotationen in den PDF-Raum und schreibt eine neue
PDF-Datei sowie einen PDF-Annotation-Sidecar. Keine Quelldatei wird verändert.
PDF-nativer Freitext-/Tabellen-Text bleibt für den `inject-pdf`-CLI-Adapter
außerhalb des Umfangs.

Für `make_pdf` ist PDF-native Textinjektion ausschließlich in diesem öffentlichen
Kompositionspfad Teil des Umfangs. Die API erhält alle Textwerte explizit; der
Seed steuert Layout, Anordnung, Seitenumbrüche und Bildrotation, nicht den
Textinhalt. Normaler Text wird als PDF-nativer Text geschrieben.

Handschriftgenerierung ist keine PDF-Aufgabe. `handwritten=True` für direkten
PDF-Text bricht mit einem eindeutigen Fehler ab, weil diese API keine sichere
Asset- oder Manifestquelle für direkt handgeschriebenen Text besitzt. Bereits
gerenderte Handschrift wird als injiziertes Bild mit Annotation übergeben; der
Composer verarbeitet sie wie jede andere Bildannotation.

Die Adaptergrenze bleibt explizit: PDF-spezifische Modelle beschreiben
Template-Seiten, Platzierung und Ausgabe-Artefakte; die gemeinsamen Modelle
`ImagePoint`, `PdfPoint` und `Quad` beschreiben die Annotationsgeometrie. Die
PDF-CLI wählt das dedizierte Paar aus und fügt dem DICOM/JPG-Runner keine
PDF-Geschäftsregeln hinzu.

## Entscheidungen

- PDF verwendet ein dediziertes Loader-/Writer-Paar für den `inject-pdf`-
  Workflow. Es ist absichtlich nicht in der DICOM/JPG-Single-Input-Registry
  registriert, weil PDF-Injektion eine PDF, ein injiziertes DICOM und eine
  Ground-Truth-Datei benötigt.
- `make_pdf` verwendet nach Möglichkeit die PDF-spezifische Loader-/Writer-
  Grenze und gemeinsame Geometriemodelle, besitzt aber eigene
  Kompositionsmodelle, weil es mehrere Bilder und Textspezifikationen statt
  eines DICOM-Runs akzeptiert.
- `reportlab` erzeugt die injizierte Ebene und `pypdf` führt sie mit dem
  Eingabe-Template zusammen. Beide sind freigegebene Runtime-Abhängigkeiten.
- Die Standardplatzierung ist `top_left`; `top_right` und ein expliziter
  unterstützter Slot-Override können für das Ziel-Template gewählt werden.
- Template-Koordinaten verwenden PDF-Punkte und einen Ursprung unten links.
  Bildkoordinaten verwenden Pixel und einen Ursprung oben links. Die
  Koordinatentypen sind nicht austauschbar.
- Aspect-Fit verkleinert das DICOM-Bild bei Bedarf und zentriert ein kleineres
  Bild in nativer Größe; es vergrößert nie. Annotationen werden auf das
  tatsächliche Platzierungsrechteck, nicht auf den konfigurierten Slot,
  abgebildet.
- Der Ausgabe-Stamm ist `output/pdf/<run_id>/<template-stem>-<slot>/`.
  Quell-PDF, DICOM und DICOM-Ground-Truth bleiben unverändert.
- PDF-Ausgabe ist bei identischen Eingaben, Konfiguration und Seed
  deterministisch; soweit das PDF-Backend dies erlaubt, werden feste Metadaten
  verwendet.
- ADR-0008 ist angenommen. Der PDF-Sidecar verwendet die gemeinsame Schema-
  Linie und die Version `0.3.0-pdf-prototype`.

## Öffentliche `make_pdf`-API

Der öffentliche Import entspricht `inject_function` und exportiert die
Eingabe- und Artefaktmodelle:

```python
from injection_pipeline import (
    PdfMakeArtifacts,
    PdfMakeImageAnnotationInput,
    PdfMakeImageInput,
    PdfMakeTextInput,
    make_pdf,
)
```

Die öffentliche Signatur lautet:

```python
def make_pdf(
    images: Sequence[PdfMakeImageInput | Mapping[str, object]],
    texts: Sequence[PdfMakeTextInput | Mapping[str, object]],
    pdf: str | PathLike[str],
    output_dir: str | PathLike[str],
    *,
    seed: int | None = None,
) -> PdfMakeArtifacts: ...
```

Beispiel:

```python
artifacts = make_pdf(
    images=[
        PdfMakeImageInput(
            path="patient-card.png",
            annotations=[
                PdfMakeImageAnnotationInput(
                    category="patient_name",
                    value="Jane Doe",
                    prefix="Name: ",
                    suffix="",
                    rendered_text="Name: Jane Doe",
                    image_corners=[
                        {"x": 20, "y": 30},
                        {"x": 180, "y": 30},
                        {"x": 180, "y": 55},
                        {"x": 20, "y": 55},
                    ],
                )
            ],
        )
    ],
    texts=[
        PdfMakeTextInput(
            category="patient_id",
            value="PID-123",
            prefix="ID: ",
            suffix="",
            handwritten=False,
        )
    ],
    pdf="template.pdf",
    output_dir="api-pdf-export",
    seed=42,
)
```

Alle Haupteingaben sind erforderlich. `images` ist eine Liste bereits
injizierter Bilddateien mit ihren Annotationen. Zur Kompatibilität werden
Dictionaries im Stil von `BoxAnnotation` akzeptiert: `label` wird auf
`category`, `text` auf `value` und `corners` auf `image_corners` abgebildet;
Legacy-Präfix- und -Suffix-Ecken bleiben erhalten, sofern vorhanden. `texts`
ist eine Liste direkter PDF-Texteinträge mit derselben Bedeutung wie
`category`, `value`, `prefix`, `suffix` und `handwritten` von `inject_function`,
jedoch ohne Ausgabepfad. `pdf` ist das Template, `output_dir` erhält die
erzeugten Artefakte.

Der Composer platziert alle Bilder und Texte ohne Überlappung. Er variiert das
Layout anhand des Seeds, einschließlich nebeneinanderliegender und gestapelter
Anordnungen, seedbarer kleiner Bildrotationen und zusätzlicher Seiten, wenn die
aktuelle Seite die verbleibenden Elemente nicht aufnehmen kann. Bei fehlerhafter
Eingabe, ungültigen Annotationen, unmöglichen Platzierungen, nicht
unterstützten PDF-Operationen oder `handwritten=True` für direkten PDF-Text
bricht er ab. Bereits gerenderte Handschrift gehört in `images`.

Der Rückgabewert ist ein `PdfMakeArtifacts`-Objekt mit erzeugter PDF, sichtbar
annotierter PDF, JSON-Sidecar und finalen Platzierungsmetadaten. Der Sidecar
speichert transformierte Bildannotation, PDF-native Textannotation,
Seitenindizes, Rotationen sowie Seed-/Layout-Metadaten zur Reproduktion. Die
Bildannotation enthalten Haupt-Quads und optionale Präfix-/Suffix-Quads, wenn
die Quellannotation diese liefert.

`make_pdf` schreibt diese Dateien direkt unter `output_dir`:

```text
pdf_make.pdf
pdf_make_annotated.pdf
pdf_make_annotations.json
```

## Ausgabe-Artefakte von `inject-pdf`

Jeder Aufruf von `inject-pdf`/`compose-pdf` schreibt:

```text
output/pdf/<run_id>/<template-stem>-<slot>/
|-- pdf_injected.pdf
|-- pdf_injected_annotated.pdf
|-- pdf_annotations.json
```

`pdf_injected.pdf` ist das Template mit der Preview des injizierten DICOM.
`pdf_injected_annotated.pdf` ergänzt sichtbare, transformierte
Annotationsumrisse. `pdf_annotations.json` enthält die transformierte PDF-
Ground-Truth und Quellenverknüpfung. Der Sidecar speichert alle Eingabepfade
und das gewählte Layout.

## Sidecar-Schema (`0.3.0-pdf-prototype`)

Der Sidecar verwendet in der einzigen ADR-0008-Linie
`record_type = "pdf_injection_run"`. Er enthält:

- Pfade von Quell-PDF, DICOM und DICOM-Ground-Truth sowie die erforderlichen
  Identitätsfelder des Quell-Runs (`source_run_id`, `source_seed` und
  `source_schema_version`),
- Template-Identifier, ausgewählter Slot, Seitenindex, Seitengröße und
  Platzierungsrechteck,
- Quellbilddimensionen und Metadaten des Bild-zu-PDF-Koordinatenraums,
- eine transformierte Vier-Ecken-Annotation für jede DICOM-Quellbox und
- Verweise auf die erzeugte PDF und die Sidecar-Dateien.

Der Sidecar muss Reihenfolge der Quellannotation und Eckenreihenfolge erhalten.
Das Laden einer fehlerhaften DICOM-Annotation schlägt über den kanonischen
`RunRecord`-Validator fehl; der PDF-Writer dupliziert keine JSON-
Validierungslogik.

## Koordinatenabbildung

Für einen Bildpunkt `(x, y)` in Pixeln und sein Platzierungsrechteck
`(left, bottom, width, height)` nach Aspect-Fit in PDF-Punkten gilt:

```text
pdf_x = left + (x / image_width_px) * width
pdf_y = bottom + height - (y / image_height_px) * height
```

Die Abbildung wird Ecke für Ecke angewendet, auch bei rotierten Polygonen. Ein
Slot außerhalb der Zielseite, ein fehlendes Quellbild oder eine Annotation
außerhalb der Quellbildgrenzen ist ein eindeutiger Konfigurations-/Validierungs-
fehler.

## Arbeitspakete

### WP-PDF-1 — Abhängigkeiten und Modelle

`reportlab` und `pypdf` hinzufügen und die Lock-Datei aktualisieren. PDF-
spezifische pydantic-Modelle für Quelleingaben, Seiten-/Slot-Geometrie,
Platzierung, Ausgabe-Artefakte und den Sidecar `0.3.0-pdf-prototype`
hinzufügen. Gemeinsame Geometriemodelle wiederverwenden.

### WP-PDF-2 — PDF- und DICOM-Laden

Den PDF-Loader als dedizierten PDF-Workflow-Adapter implementieren. Er muss
unlesbare oder leere PDFs zurückweisen und Seitengröße/-anzahl bereitstellen.
Den vorhandenen DICOM-Loader für das injizierte DICOM wiederverwenden und sein
`ground_truth.json` über `load_run_record` laden.

### WP-PDF-3 — Platzierung und Koordinatentransformation

Slot-Auflösung, Seitenbegrenzungsprüfungen, Aspect-Fit-Platzierung und die
Bild-zu-PDF-Abbildung implementieren. Nichtquadratische Bilder,
Seitenverhältnisabweichungen, Zentrierung in nativer Größe und rotierte Quads
mit Unit-Tests abdecken.

### WP-PDF-4 — PDF-Schreiben

Das reportlab-Overlay erzeugen, es mit `pypdf` auf der ausgewählten Eingabe-
PDF-Seite zusammenführen und den PDF-Sidecar ausgeben. Alle Eingabeseiten und
PDF-Metadaten erhalten, außer wenn der Writer für Determinismus flüchtige
Producer-Felder ersetzen muss.

### WP-PDF-5 — CLI und Integration

`inject-pdf` (mit dem Alias `compose-pdf`) ergänzen; erforderlich sind
`--input-pdf`, `--input-dicom` und `--dicom-annotation`, optional
`--output-dir`, `--slot` und `--page-index`. Das bestehende DICOM/JPG-CLI-Verhalten bleibt
unverändert. Erzeugte PDF- und Sidecar-Pfade ausgeben. Die Adapter-Einstiege sind
`PdfLoader.load` und `PdfWriterAdapter.write`.

### WP-PDF-6 — Tests, Fixture und lokale Validierung

Synthetische versionierte Fixtures für Unit-/Integrationstests verwenden.
Zusätzlich einen lokalen Smoke-Test mit einem DICOM aus
`DicomData/Dicom-Files` ausführen, Ergebnis und Annotation unter
`DicomData/InjectedDicom` schreiben und die vorhandene PDF unter
`DicomData/pdf` verwenden. Lokal erzeugte Daten werden ignoriert und nicht
versioniert.

### WP-PDF-7 — Dokumentation und Provenienz

Adapter-Vertrag, Zielarchitektur, DICOM-Betriebsleitfaden sowie Schema-/Domain-
Dokumentation aktualisieren. Das ADR-0008-Schema-Änderungsprotokoll ergänzen
und die Entscheidung als angenommen markieren.

## Erforderliche Tests und Gates

- Der PDF-Loader weist fehlende, unlesbare und leere Eingaben zurück.
- Die Verknüpfung von DICOM und Annotation wird vor dem Schreiben validiert.
- Alle PDF-Quellseiten bleiben in der Ausgabe erhalten.
- Eine Seitenverhältnisabweichung bildet Ecken innerhalb des gezeichneten
  Bildes ab, nicht nur innerhalb des konfigurierten Slots.
- Bildpunkte oben links und unten rechts werden auf die entsprechenden
  Platzierungsecken abgebildet; die Invertierung der y-Achse wird abgedeckt.
- Rotierte Polygone behalten die Punktreihenfolge.
- Slot-/Seitengrenzen und Fehler wegen fehlender Previews sind eindeutig.
- Ausgabe-PDF und Sidecar sind nicht leer, und die Sidecar-Validierung ist
  erfolgreich.
- Wiederholte Läufe mit identischen Eingaben erzeugen identischen Sidecar-
  Inhalt und, soweit unterstützt, deterministische PDF-Bytes.
- Bestehende DICOM/JPG-Unit-, Integrations-, ruff- und mypy-Gates bleiben
  erfolgreich.
