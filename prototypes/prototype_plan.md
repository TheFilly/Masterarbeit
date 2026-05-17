# Prototype Plan - DICOM Injection Prototype

## Ziel

Dieser Plan steuert den aktuellen Quick-and-Dirty-DICOM-Prototyp in `prototypes/dicom/`.
Er dient als Machbarkeitsnachweis fuer injizierbare DICOM-Tags, sichtbare Pixel-Injektion im
begrenzten Echo-/US-Setting und ein proto-stabiles Ground-Truth-Artefakt, ohne bereits das finale
Produktionsdesign in `src/` festzuschreiben.

`PLAN.md` bleibt die uebergeordnete Projekt-Roadmap. Diese Datei enthaelt nur den aktiven
Arbeitsstand und die noch offenen Aufgaben fuer den DICOM-Prototyp.

## Status

- Scope: nur aktueller DICOM-Prototyp in `prototypes/dicom/`
- Status: aktiv
- Letzte Aktualisierung: 2026-05-17
- Hauptziel: die Prototype-Erkenntnisse in ein belastbares Schema- und Handover-Artefakt fuer die
  spaetere Phase-2-Modellierung ueberfuehren

## Beschlossener MVP-Rahmen

- Modalitaets-Scope: zunaechst nur das bestehende Echo-/US-Beispiel
- Sichtbare Pixel-Injektion: `PatientName`, `PatientID` und `AccessionNumber`
- Nur als DICOM-Tag: `PatientBirthDate` und `PatientSex`
- Standardmodus: DICOM-Tag-Injektion und sichtbarer Overlay-Text gemeinsam in einem Lauf
- Rotation: kleine diskrete Menge, bewusst begrenzt; keine freie Rotation im MVP
- Sichtbare Geometrie: `corners` ist die Standardform fuer sichtbare Annotationen
- Schemaziel: proto-stabil, aber noch keine verbindliche `src/`-API
- Run-Ordner: enthalten mindestens Seed, Winkel, Platzierungsmodus, Beispielart und kurze ID
- Preview: standardisiertes Artefakt pro Run, nicht nur Debug-Helfer

## Aktueller Ist-Stand

Stand auf Basis von `AGENTS.md`, Root-`PLAN.md`, `prototypes/dicom/README.md`,
`prototypes/dicom/inject.py`, `prototypes/dicom/pixel_injection.py`,
`prototypes/dicom/view.py` und den validierten Beispiel-Runs unter
`prototypes/dicom/output_validation_small/`,
`prototypes/dicom/output_validation_large/` und
`prototypes/dicom/output_validation_main/`.

- Der Prototyp injiziert reproduzierbar fuenf DICOM-Tags in eine Echo-DICOM-Datei.
- Sichtbare Pixel-Injektion ist fuer `PatientName`, `PatientID` und `AccessionNumber` umgesetzt.
- `PatientBirthDate` und `PatientSex` bleiben tag-only.
- `--font-size-pct` wirkt funktional auf sichtbare Textgroesse und Box-Geometrie.
- `--placement-mode` ist auf `corners` oder `free` stellbar.
- `--font-family` ist implementiert und bewusst auf feste Choices begrenzt:
  `arial`, `calibri`, `tahoma`, `consolas`.
- `--text-background` ist prototype-spezifisch implementiert und unterstuetzt aktuell optional
  nur `white`.
- Run-Ordner folgen dem Schema `seed{seed:04d}-angle{angle:03d}-{mode}-echo-{short_id}`.
- Pro Run entstehen aktuell fuenf Artefakte:
  `*_injected.dcm`, `preview.png`, `preview_annotated.png`, `ground_truth.json`,
  `run_manifest.json`.
- `preview_annotated.png` zeichnet die roten Kontroll-Boxes mit duennerer Linie.
- `box_annotations` trennen jetzt zwischen annotiertem `text` und sichtbarem `rendered_text`.
- Bei `SYNTH-433218` und `ACC-0013389` markiert `text` nur den PII-Teil, waehrend
  `rendered_text` den voll sichtbaren Token behaelt.
- `render_metadata` fuehrt jetzt Stil- und Geometriedetails wie Font-Familie, effektive
  Font-Groesse, Hintergrundstatus/-farbe, `text_segments`, PII-Bounds und
  `rendered_text_corners` mit.
- `inject.py` bleibt bewusst Prototype-Orchestrierung und ist keine Vorlage fuer die finale
  Pipeline-Struktur in `src/`.

## Eingefrorene Ergebnisse

Diese Punkte gelten im Prototyp derzeit als erreicht und muessen nicht weiter als operative
Arbeitspakete in diesem Plan gefuehrt werden:

- Prototype-Stand ist im README beschrieben.
- Sichtbare Pixel-Injektion fuer den MVP ist umgesetzt.
- Platzierung und Rotation sind begrenzt und reproduzierbar.
- Das Ground-Truth-Artefakt ist proto-stabil genug fuer den aktuellen Prototype.
- Die Output-Struktur pro Run ist standardisiert.
- Die Mini-Erweiterung fuer Font-Auswahl, optionalen Text-Hintergrund, wirksame
  Schriftgroessensteuerung und PII-only-Bounding-Boxes ist implementiert und validiert.

## Offene Arbeitspakete


### 1. Vereinheitlichtes Annotationsschema entwerfen

- Ein prototypisches, formatuebergreifendes Schema definieren, das drei Arten von Annotationen
  sauber unterscheiden kann:
  - `span_annotations` fuer Text, CSV, Dateinamen, Ordnernamen und andere inline markierte Inhalte
  - `box_annotations` fuer sichtbare PHI in bildbasierten DICOM-/PDF-Artefakten mit `corners` und
    `region`
  - `dicom_tag_annotations` fuer reine DICOM-Tag-Injektionen ohne 2D-Koordinaten
- Das Schema an den bereits beobachteten Datenmustern ausrichten:
  - Inline-Tags wie `<PER>...</PER>`, `<DATE>...</DATE>`, `<AGE>...</AGE>`
  - Sidecar-CSV oder vergleichbare Box-Daten mit `field`, `text`, `region`, Geometrie
  - aktuelles Prototype-Ground-Truth-Artefakt fuer DICOM-Tag-Injektionen

**Pflichtfelder fuer gemeinsame Metadaten**

- `source_file`
- `output_file`
- `modality` oder `document_type`
- `seed`
- `rotation_degrees`
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
- `corners` als Standardform fuer sichtbare Box-Annotationen, insbesondere bei Rotation
- `region`
- optional `rendered_text`, wenn sichtbarer Token und annotierter PII-Teil auseinanderfallen
- optional `rotation_degrees`
- optional `polygon`, falls spaeter mehr als vier Eckpunkte benoetigt werden
- optional `page` oder `frame_index`

**Pflichtfelder fuer `dicom_tag_annotations`**

- `tag_address`
- `tag_keyword`
- `dicom_vr`
- `value`
- `identity_field`

**Designentscheidungen**

- Bounding Boxes sind nur fuer sichtbare Pixel-/Render-PHI relevant, nicht fuer reine
  DICOM-Tag-Injektion.
- Reine DICOM-Tag-Injektionen bleiben ueber Tag-Metadaten adressiert, nicht ueber 2D-Koordinaten.
- Fuer den Prototype sollen Bounding Boxes so genau wie praktikabel erfasst werden; `corners` ist
  die Standardform fuer sichtbare Annotationen, besonders bei Rotation.
- Das aktuelle Prototype-Verhalten trennt bei praefixierten sichtbaren Tokens zwischen
  annotiertem PII-`text` und sichtbarem `rendered_text`.
- Das Schema bleibt proto-stabil: stark genug fuer weitere Prototype-Schritte und die
  Phase-2-Vorbereitung, aber noch kein finaler Vertrag fuer `src/injection_pipeline/models/`.

**Akzeptanznahe Outputs**

- Es gibt ein JSON-kompatibles Prototype-Schema oder einen gleichwertigen Modellvorschlag.
- Das bestehende Ground-Truth-Artefakt laesst sich nachvollziehbar auf das neue Schema abbilden.
- Die Trennung zwischen Prototype-Schema und spaeterem produktionsreifem Modell in `src/` bleibt
  explizit.

### 2. Anschluss an Phase 2 vorbereiten

- Herausarbeiten, welche Prototype-Erkenntnisse spaeter in das abstrakte Dokument- und
  Annotationsmodell einfliessen sollen.
- Offene Punkte markieren, die vor einer Uebernahme in `src/` entschieden werden muessen.
- Explizit festhalten, dass Echo-/US-Heuristiken, aktuelle Positionsszenarien,
  Prototype-Fontwahl, optionaler Text-Hintergrund und Prototype-Orchestrierung nicht automatisch
  in `src/` uebernommen werden.

**Akzeptanznahe Outputs**

- Es gibt eine Liste uebernehmbarer Prototype-Erkenntnisse.
- Es gibt eine Liste offener Architekturentscheidungen fuer Phase 2 und Phase 3.
- Prototype-spezifische Entscheidungen und uebertragbare Prinzipien sind getrennt aufgefuehrt.

## Akzeptanzkriterien

- Diese Datei ist der eindeutige aktive Arbeitsplan fuer den aktuellen DICOM-Prototyp.
- Erledigte Prototype-Aufgaben werden hier nicht mehr als offene Arbeitspakete gefuehrt.
- Der Root-`PLAN.md` verweist implizit auf diese Datei als operativen Prototype-Backlog und traegt
  selbst keine Detailaufgaben des DICOM-Prototyps.
- Das geplante Annotationsschema deckt explizit `span_annotations`, `box_annotations` und
  `dicom_tag_annotations` ab.
- Die Trennung zwischen Prototype-Design und produktionsreifer Implementierung in `src/` bleibt
  klar.

## Annahmen

- Der Scope dieser Datei umfasst nur den aktuellen DICOM-Prototyp.
- Das vereinheitlichte Annotationsschema wird zunaechst als Prototype-/Design-Artefakt geplant.
- Eine spaetere produktive Modellierung in `src/injection_pipeline/models/` erfolgt erst nach
  gesonderter Architekturentscheidung.
