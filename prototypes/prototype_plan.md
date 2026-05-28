# Prototype Plan - DICOM Injection Prototype

## Ziel

Dieser Plan steuert den aktuellen Quick-and-Dirty-DICOM-Prototyp in `prototypes/dicom/`.
Er dient als Machbarkeitsnachweis fuer injizierbare DICOM-Tags, sichtbare Pixel-Injektion im
begrenzten Echo-/US-Setting und ein proto-stabiles Ground-Truth-Artefakt, ohne bereits das finale
Produktionsdesign in `src/` festzuschreiben.

`PLAN.md` bleibt die uebergeordnete Projekt-Roadmap. Diese Datei enthaelt nur den aktiven
Arbeitsstand und die noch offenen Aufgaben fuer den DICOM-/JPG-Prototyp.

## Status

- Scope: aktueller Prototype in `prototypes/dicom/`
- Status: aktiv
- Letzte Aktualisierung: 2026-05-28
- Hauptziel: die Prototype-Erkenntnisse in ein belastbares Schema- und Handover-Artefakt fuer die
  spaetere Phase-2-Modellierung ueberfuehren

## Aktueller Ist-Stand

- Der Prototyp injiziert reproduzierbar fuenf DICOM-Tags in eine Echo-DICOM-Datei.
- Sichtbare Pixel-Injektion ist fuer `PatientName`, `PatientID` und `AccessionNumber` umgesetzt.
- `PatientBirthDate` und `PatientSex` bleiben tag-only.
- `inject.py` unterstuetzt jetzt `.dcm`, `.jpg` und `.jpeg`.
- `--show-label-boxes y|n` steuert die zusaetzliche Darstellung generischer Label-Boxes.
- `label_corners` markieren bei praefixierten sichtbaren Tokens zusaetzlich das generische
  Segment (`SYNTH-`, `ACC-`); fuer `PatientName` bleibt das Feld leer bzw. `null`.
- Sichtbare `corners` und `label_corners` werden jetzt maskenbasiert aus der final rotierten
  Render-Maske abgeleitet; Platzierung und Annotation nutzen dieselbe Overlay-Geometriequelle.
- `render_metadata` dokumentiert die neue Geometrie explizit ueber
  `geometry_source = "mask_bbox_after_final_rotation"` und `mask_alpha_threshold`.
- Run-Ordner folgen jetzt dem Schema
  `{filetype}-{ddmmyyyy}-{hhmm}-seed{seed:04d}-angle{angle:03d}-{mode}-fs{fontsize}-{fontfamily}-{textbg}`.
- Neue Verifikations-Runs liegen unter `output_validation_dcm_label_y`,
  `output_validation_dcm_label_n`, `output_validation_jpg`, `output_validation_ap6_dcm_a`,
  `output_validation_ap6_dcm_b` und `output_validation_ap6_jpg`.

## Eingefrorene Ergebnisse

- Arbeitspaket 3 ist umgesetzt: `label_corners` liegen im Ground Truth vor und koennen optional
  in `preview_annotated.png` visualisiert werden.
- Arbeitspaket 4 ist umgesetzt: JPG-Input laeuft ueber einen separaten sichtbaren Renderpfad
  ohne DICOM-Tag-Injektion.
- Arbeitspaket 5 ist umgesetzt: neue Run-Ordner und `run_id` folgen dem erweiterten Schema;
  bestehende alte Ordner bleiben unveraendert.
- Arbeitspaket 6 ist umgesetzt: sichtbare Bounding-Boxes werden aus getrennten, final rotierten
  Render-Masken fuer Volltext, PII-Teil und optionales Label abgeleitet; aktivierter
  Text-Hintergrund vergroessert die PII-Box nicht auf das Hintergrundrechteck.

## Offene Arbeitspakete

- Arbeitspaket 1 bleibt offen: vereinheitlichtes Annotationsschema entwerfen
- Arbeitspaket 2 bleibt offen: Anschluss an Phase 2 vorbereiten

## Naechste fachliche Schwerpunkte

### Abgeschlossene Verifikation zu Arbeitspaket 6

**Umgesetzt:** Die sichtbaren Bounding Boxes fuer Text-Overlays werden nicht mehr aus
 Font-Metriken rekonstruiert, sondern aus getrennten, final rotierten Masken fuer
 `rendered_text`, PII-Teil und optionales Label gewonnen. Die Overlay-Platzierung laeuft jetzt
 ueber dieselbe vorbereitete Geometrie wie die spaetere Annotation.

**Erreichte Punkte**

- `pixel_injection.py` fuehrt getrennte Masken fuer Volltext, PII-Teil und optionales Label.
- `box_annotations[].corners` und `label_corners` werden aus final rotierten Masken abgeleitet.
- `render_metadata` dokumentiert `geometry_source = "mask_bbox_after_final_rotation"` sowie den
  verwendeten `mask_alpha_threshold`.
- `_materialize_positions()` nutzt dieselbe vorbereitete Overlay-Geometrie wie die finale
  Annotation und vermeidet damit systematische Offsets.
- `text_background white` bleibt fuer die sichtbare Lesbarkeit relevant, vergroessert aber die
  PII-Box nicht kuenstlich auf das Hintergrundrechteck.

**Verifikation**

- `uv run python -m py_compile prototypes/dicom/pixel_injection.py tests/unit/test_pixel_injection_corners.py`
  laeuft erfolgreich.
- Zwei identische DCM-Runs unter `output_validation_ap6_dcm_a` und
  `output_validation_ap6_dcm_b` liefern identische `box_annotations`,
  `render_metadata.visible_render_plan` und `render_metadata.visible_annotations`.
- Ein separater JPG-Run unter `output_validation_ap6_jpg` bestaetigt denselben sichtbaren
  Renderpfad ohne DICOM-Tag-Injektion.
- Die reguleren `pytest`- und `ruff`-Laeufe konnten im aktuellen Environment nicht ausgefuehrt
  werden, weil `pytest` und `ruff` in der vorhandenen `.venv` derzeit nicht installiert sind.

---


## Später umsetzen, wenn prototyp fertig (vorerst ignorieren)

### 1. Vereinheitlichtes Annotationsschema entwerfen

- `span_annotations`, `box_annotations` und `dicom_tag_annotations` sauber gegeneinander abgrenzen
- Pflichtfelder fuer gemeinsame Metadaten und format-spezifische Annotationstypen definieren
- Prototype-Schema klar von einer spaeteren produktionsreifen `src/`-API trennen

### 2. Anschluss an Phase 2 vorbereiten

- Uebernehmbare Prototype-Erkenntnisse fuer spaetere Modelle herausarbeiten
- Offene Architekturentscheidungen fuer Phase 2 und 3 markieren
- Prototype-spezifische Heuristiken explizit von uebertragbaren Prinzipien trennen

## Akzeptanzkriterien

- Diese Datei ist der eindeutige aktive Arbeitsplan fuer den aktuellen DICOM-Prototyp.
- Erledigte Prototype-Aufgaben werden hier nicht mehr als offene Arbeitspakete gefuehrt.
- Das geplante Annotationsschema deckt explizit `span_annotations`, `box_annotations` und
  `dicom_tag_annotations` ab.
- Die Trennung zwischen Prototype-Design und produktionsreifer Implementierung in `src/` bleibt
  klar.
