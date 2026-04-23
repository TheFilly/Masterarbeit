# Prototype Plan - DICOM Injection Prototype

## Ziel

Dieser Plan steuert den aktuellen Quick-and-Dirty-DICOM-Prototyp in `prototypes/dicom/`.
Er dient als Machbarkeitsnachweis fuer injizierbare DICOM-Tags, reproduzierbare synthetische
Identitaeten und ein Ground-Truth-Artefakt, ohne bereits das finale Produktionsdesign in `src/`
festzuschreiben.

`PLAN.md` bleibt die zentrale Projekt-Roadmap. Diese Datei enthaelt nur die operativen Aufgaben
und Entscheidungen fuer den aktuellen DICOM-Prototyp.

## Status

- Scope: nur aktueller DICOM-Prototyp
- Status: aktiv
- Hauptziel: DICOM-Tag-Injektion und Annotationsartefakte soweit konkretisieren, dass spaetere
  Modell- und Pipeline-Entscheidungen vorbereitet werden

## Backlog

### 1. Prototype-Stand dokumentieren

- Bestehenden Prototyp in `prototypes/dicom/` als Ausgangsbasis stabil beschreiben
- Festhalten, welche DICOM-Tags derzeit injiziert werden
- Abgrenzen, was aktuell nur Prototype ist und spaeter verworfen oder in `src/` ueberfuehrt wird

**Erwartete Outputs**

- Konsistente Beschreibung von Input, Output und Seed-Verhalten
- Klare Trennung zwischen wiederverwendbaren Teilen und Wegwerf-Orchestrierung

### 2. Pixel-Injektion im DICOM-Bild ergaenzen

- Den Prototyp von reiner DICOM-Tag-Injektion auf sichtbare Injektion im Pixelraum erweitern
- Identifiers nicht nur in Metadaten, sondern direkt im DICOM-Bild rendern
- Klar trennen, welche Inhalte als DICOM-Tag, welche als sichtbarer Overlay-Text und welche in beiden
  Formen injiziert werden

**Erwartete Outputs**

- Prototype-Konzept fuer Pixel-Injektion in DICOM-Bilder
- Liste der zuerst zu unterstuetzenden sichtbaren Identifier-Typen
- Dokumentierte Abgrenzung zwischen Tag-Injektion und Pixel-Injektion

### 3. Variierende Platzierung und Rotation unterstuetzen

- Injizierte Daten an verschiedenen Positionen im Bild platzieren, statt nur an einem festen Ort
- Rotation als Prototype-Variante vorsehen, damit sichtbare PHI nicht nur horizontal erscheint
- Seed-gesteuerte Steuerung fuer Position, Layout-Variante und Rotation festlegen
- Sicherstellen, dass die Injektionen plausibel in headernahen oder overlaysensiblen Bildbereichen
  erscheinen, ohne den gesamten Bildinhalt unbrauchbar zu machen

**Erwartete Outputs**

- Kleine Menge definierter Layout- und Positionsvarianten fuer den Prototype
- Prototype-Regeln fuer optionale Rotation injizierter Inhalte
- Reproduzierbare Platzierungsstrategie auf Basis des Seeds

### 4. Ground-Truth-Artefakt schaerfen

- Pruefen, ob das aktuelle `ground_truth.jsonl` fuer reine DICOM-Tag-Injektionen ausreichend ist
- Fehlende Metadaten fuer spaetere Validierung und Vergleichbarkeit identifizieren
- Festhalten, welche Felder Prototype-spezifisch bleiben duerfen
- Die moeglichst genauen Bounding Boxes der sichtbaren Injektionen als Pflichtbestandteil des
  Prototype-Artefakts aufnehmen
- Festlegen, wie Bounding Boxes fuer rotierte oder mehrzeilige Injektionen erfasst werden
- `corners` als Standardform fuer sichtbare Annotationen festlegen, damit die Geometrie nicht auf
  eine ungenaue achsenparallele Box reduziert wird

**Erwartete Outputs**

- Kleine Soll-Ist-Liste fuer das aktuelle Prototype-`ground_truth.jsonl`
- Vorschlag, welche Felder fuer den naechsten Prototype-Schritt stabilisiert werden sollen
- Bounding-Box-Regeln fuer sichtbare Injektionen mit moeglichst hoher Genauigkeit

### 5. Vereinheitlichtes Annotationsschema entwerfen

- Ein prototypisches, formatuebergreifendes Schema definieren, das drei Arten von Annotationen
  sauber unterscheiden kann:
  - `span_annotations` fuer Text, CSV, Dateinamen, Ordnernamen und andere inline markierte Inhalte
  - `box_annotations` fuer sichtbare PHI in bildbasierten DICOM-/PDF-Artefakten mit `corners` und
    `region`
  - `dicom_tag_annotations` fuer reine DICOM-Tag-Injektionen ohne 2D-Koordinaten
- Das Schema explizit an den bereits beobachteten Datenmustern ausrichten:
  - Inline-Tags wie `<PER>...</PER>`, `<DATE>...</DATE>`, `<AGE>...</AGE>`
  - Sidecar-CSV mit `field`, `text`, `region`, `x`, `y`, `width`, `height`, die fuer den Prototype
    in `corners` ueberfuehrt oder daraus abgeleitet werden
  - Aktuelles Prototype-`ground_truth.jsonl` fuer DICOM-Tag-Injektionen

**Pflichtfelder fuer gemeinsame Metadaten**

- `source_file`
- `output_file`
- `modality` oder `document_type`
- `seed`
- `run_id`
- `identity_id`

**Pflichtfelder fuer `span_annotations`**

- `label`
- `text`
- `start`
- `end`
- `container` oder `field_name`

**Pflichtfelder fuer `box_annotations`**

- `label`
- `text`
- `region`
- `corners` als Standardform fuer sichtbare Box-Annotationen, insbesondere bei Rotation
- optional `rotation_degrees`
- optional `polygon`, falls spaeter mehr als vier Eckpunkte benoetigt werden
- optional `page` oder `frame_index`

**Pflichtfelder fuer `dicom_tag_annotations`**

- `tag_address`
- `tag_keyword`
- `dicom_vr`
- `value`
- `identity_field`

**Designentscheidung**

- Bounding Boxes sind nur fuer sichtbare Pixel-/Render-PHI relevant, nicht fuer reine
  DICOM-Tag-Injektion.
- Reine DICOM-Tag-Injektionen bleiben ueber Tag-Metadaten adressiert, nicht ueber 2D-Koordinaten.
- Fuer den Prototype sollen Bounding Boxes so genau wie praktikabel erfasst werden; `corners` ist
  die Standardform fuer sichtbare Annotationen, besonders bei Rotation.

**Erwartete Outputs**

- Vorschlag fuer ein gemeinsames Pydantic-Modell oder JSON-kompatibles Prototype-Schema
- Mapping-Regeln vom bestehenden Prototype-`ground_truth.jsonl` auf das neue Schema
- Klare Abgrenzung zwischen DICOM-Tag-Injektion, Text-Span und Pixel-/Header-Overlay

### 6. Output-Struktur pro Injektionslauf standardisieren

- Fuer jede Injektion oder jeden Prototype-Run einen eigenen Sub-Ordner unter `output/` erzeugen
- Den Sub-Ordner reproduzierbar benennen, mindestens anhand von Seed und einem weiteren stabilen
  Identifier
- Annotationen und injizierte Zieldokumente gemeinsam in diesem Run-Ordner ablegen
- Optional zusaetzliche Vorschauartefakte oder Debug-Informationen im selben Run-Ordner sammeln,
  solange die Kernartefakte klar erkennbar bleiben

**Erwartete Outputs**

- Konvention fuer Run-spezifische Output-Pfade
- Klare Benennung fuer Seed plus weiterem Identifier
- Gemeinsame Ablage von injiziertem Dokument und Annotationsartefakt pro Run

### 7. Anschluss an Phase 2 vorbereiten

- Herausarbeiten, welche Prototype-Erkenntnisse spaeter in das abstrakte Dokument- und
  Annotationsmodell einfliessen sollen
- Offene Punkte markieren, die vor einer Uebernahme in `src/` entschieden werden muessen

**Erwartete Outputs**

- Liste uebernehmbarer Prototype-Erkenntnisse
- Liste offener Architekturentscheidungen fuer Phase 2 und Phase 3

## Akzeptanzkriterien

- Diese Datei ist der eindeutige Arbeitsplan fuer den aktuellen DICOM-Prototyp
- Der Root-`PLAN.md` verweist auf diese Datei, ohne operative Prototype-Aufgaben selbst zu tragen
- Das geplante Annotationsschema deckt explizit Inline-/Span-Annotationen, Bounding-Box-Annotationen
  und DICOM-Tag-Annotationen ab
- Pixel-Injektion, variable Platzierung, Rotation und run-basierte Output-Ordner sind als
  konkrete Arbeitspakete beschrieben
- Die Trennung zwischen Prototype-Design und produktionsreifer Implementierung in `src/` bleibt klar

## Feedback und sinnvolle Erweiterungen

- Pixel-Injektion ist fuer den Prototyp sehr wertvoll, weil sie den Abstand zwischen reiner
  Metadatenmanipulation und realistisch sichtbarer PHI deutlich verkleinert.
- Rotation ist sinnvoll, sollte aber im Prototype bewusst begrenzt werden, zum Beispiel auf wenige
  diskrete Winkel, damit Annotation, Rendering und spaetere Validierung beherrschbar bleiben.
- Fuer Bounding Boxes ist es sinnvoll, `corners` als einzige geometrische Standardform zu nutzen.
  Reine `x/y/width/height`-Angaben werden bei gedrehtem Text schnell ungenau.
- Die run-basierte Output-Struktur ist eine gute Idee, weil sie Reproduzierbarkeit, Debugging und
  spaetere Vergleichslaufe stark erleichtert.

**Weitere sinnvolle Ideen fuer den Prototypen**

- Zusaetzlich ein kleines Render-Metadatenartefakt pro Run speichern, zum Beispiel Schriftgroesse,
  Rotation, Position und verwendete Textbausteine
- Eine einfache Kollisionspruefung vorsehen, damit injizierter Text nicht ueber bereits vorhandene
  Overlays oder wichtige Bildbereiche geschrieben wird
- Eine Preview-Ausgabe pro Run standardisieren, damit Bounding Boxes und sichtbare Injektion schnell
  manuell kontrolliert werden koennen
- Eine kleine Menge definierter Szenarien einfuehren, zum Beispiel `header_clean`,
  `header_dense`, `rotated_overlay`, damit der Prototype gezielt vergleichbar bleibt
- Den Prototype frueh auf Mehrfachinjektionen pro Bild auslegen, damit nicht spaeter von einem
  Ein-Injektions-Modell auf ein Mehr-Injektions-Modell umgebaut werden muss

## Annahmen

- Der Scope dieser Datei umfasst nur den aktuellen DICOM-Prototyp
- Das vereinheitlichte Annotationsschema wird zunaechst als Prototype-/Design-Artefakt geplant
- Eine spaetere produktive Modellierung in `src/injection_pipeline/models/` erfolgt erst nach
  gesonderter Architekturentscheidung
