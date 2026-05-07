# Prototype Plan - DICOM Injection Prototype

## Ziel

Dieser Plan steuert den aktuellen Quick-and-Dirty-DICOM-Prototyp in `prototypes/dicom/`.
Er dient als Machbarkeitsnachweis fuer injizierbare DICOM-Tags, sichtbare Pixel-Injektion im
begrenzten Echo-/US-Setting und ein proto-stabiles Ground-Truth-Artefakt, ohne bereits das finale
Produktionsdesign in `src/` festzuschreiben.

`PLAN.md` bleibt die zentrale Projekt-Roadmap. Diese Datei enthaelt nur die operativen Aufgaben
und Entscheidungen fuer den aktuellen DICOM-Prototyp.

## Status

- Scope: nur aktueller DICOM-Prototyp
- Status: aktiv
- Hauptziel: den bestehenden Tag-Injektions-Prototyp zu einem begrenzten, aber klar dokumentierten
  MVP fuer kombinierte DICOM-Tag- und sichtbare Pixel-Injektion weiterentwickeln

## Beschlossener MVP-Rahmen

- Modalitaets-Scope: zunaechst nur das bestehende Echo-/US-Beispiel; spaetere Erweiterung auf
  andere DICOM-Arten bleibt ausdruecklich offen
- Sichtbare Pixel-Injektion: `PatientName`, `PatientID` und `AccessionNumber`
- Nur als DICOM-Tag: `PatientBirthDate` und `PatientSex`
- Standardmodus: DICOM-Tag-Injektion und sichtbarer Overlay-Text gemeinsam in einem Lauf
- Rotation: kleine diskrete Menge, bewusst begrenzt; keine freie Rotation im MVP
- Sichtbare Geometrie: `corners` ist die Standardform fuer sichtbare Annotationen
- Schemaziel: proto-stabil, also wiederverwendbar als Design-Artefakt, aber noch keine verbindliche
  `src/`-API
- Run-Ordner: enthalten mindestens Seed, Winkel, Beispielart und eine kurze ID
- Preview: standardisiertes Artefakt pro Run, nicht nur Debug-Helfer

## Ist-Stand (Stand: 2026-05-07)

- Der Prototyp injiziert reproduzierbar fuenf DICOM-Tags in genau eine Echo-DICOM-Datei
- Sichtbare Pixel-Injektion ist fuer `PatientName`, `PatientID` und `AccessionNumber` umgesetzt
- `PatientBirthDate` und `PatientSex` bleiben tag-only
- Schriftgroesse per `--font-size-pct` (Prozentsatz, Default 100, >= 1)
- Platzierungsmodus per `--placement-mode`: `corners` (seed-gesteuert zufaellige Ecke) oder
  `free` (unabhaengige Zufallsposition je Annotation, seed-gesteuert)
- Run-Ordner-Benennung: `seed{:04d}-angle{:03d}-{mode}-{type}-{short_id}`
- Pro Run fuenf Artefakte: injiziertes DICOM, `preview.png`, `preview_annotated.png` (rote
  Bounding Boxes), `ground_truth.jsonl`, `run_manifest.json`
- Ground-Truth-Schema proto-stabil: `box_annotations` enthalten `corners`, `frame_index`,
  `font_size_pct`; `run_metadata` und `render_metadata` als eigene Top-Level-Felder
- DICOM-Quelldatei: 58-Frame Echo/US (708x1016, `YBR_FULL_422`); Ausgabe als `RGB`
- `inject.py` ist weiterhin Quick-and-Dirty-Orchestrierung, kein Vorlage fuer `src/`
- Wiederverwendbare Logik: `identity.py`, `dicom_writer.py`, Rendering-Primitives in
  `pixel_injection.py` (ohne Placement-Heuristik)

## Arbeitspakete


### 0. Neue Features

#### A — Variable Schriftgroesse (`--font-size-pct`)

**`inject.py`**
- Neues CLI-Argument: `--font-size-pct`, Typ `int`, Default `100`, Metavar `PERCENT`.
  Validation nach `parse_args()`: Wert `< 1` → `ValueError`.
- Wert durch `_run_pixel_injection()` → `inject_visible_text()` durchreichen.
- In `_build_record()`: `"font_size_pct"` in `render_metadata` aufnehmen.

**`pixel_injection.py`**
- Modulkonstante: `_DEFAULT_FONT_SIZE_PX: int = 18` (single source of truth fuer 100 %).
- Neue Funktion: `_resolve_font_size_px(font_size_pct: int) -> int`
  → `max(1, round(18 * pct / 100))`, `ValueError` bei `< 1`.
- `load_default_font()` bekommt Parameter `font_size_px: int`, nutzt ihn statt Hardcode.
  PIL-Fallback ignoriert den Wert (kein Crash).
- `_materialize_positions()`, `render_visible_annotations()`, `inject_visible_text()`
  bekommen `font_size_pct: int` (Default `100`).
  Alle Bounding-Box-Messungen muessen den aufgeloesten Font nutzen.

**Annotation JSON**
- Jeder `box_annotation`-Eintrag bekommt `"font_size_pct": <int>`.
- `render_metadata.visible_annotations[*].render_metadata.font_size` bleibt und traegt
  die aufgeloeste Pixel-Groesse.

**Akzeptanzkriterien**
- `--font-size-pct 100` erzeugt identische Ausgabe wie vor der Aenderung.
- `--font-size-pct 50` erzeugt sichtbar kleineren Text und kleinere Corners in der Annotation.
- `--font-size-pct 0` crashed mit `ValueError` ohne Dateien zu schreiben.
- Gleicher Seed + gleicher Prozentwert → identische Ausgabe.

---

#### B — Zufaellige Platzierung (`--placement-mode`)

**`inject.py`**
- Neues CLI-Argument: `--placement-mode`, Typ `str`, Default `"corners"`,
  `choices=["free", "corners"]`.
- `_build_run_id()` bekommt `placement_mode: str`. Neues Format:
  `seed{seed:04d}-angle{angle:03d}-{placement_mode}-echo-{short_id}`
  (Beispiel: `seed0042-angle020-corners-echo-91180014`). Breaking change — alte Ordner
  werden nicht umbenannt.
- In `_build_record()`: `"placement_mode"` in `run_metadata` und `render_metadata`.

**`pixel_injection.py`**
- Modulkonstante: `_VALID_PLACEMENT_MODES: tuple[str, ...] = ("free", "corners")`.
- `inject_visible_text()` bekommt `placement_mode: str` (Default `"corners"`),
  validiert gegen `_VALID_PLACEMENT_MODES`.
- `rng = random.Random(seed)` wird direkt vor `_materialize_positions()` konstruiert
  und als Parameter uebergeben. Kein globales `random.seed()`.
- `_materialize_positions()` bekommt `placement_mode: str` und `rng: random.Random`:
  - **"corners"**: Einmaliger `rng.choice(["top_left","top_right","bottom_left","bottom_right"])`.
    Alle Annotationen werden in dieser Ecke gestapelt (oben → nach unten, unten → nach oben).
    Margin: `max(24, int(w * 0.03))`.
  - **"free"**: Pro Annotation ein unabhaengiges `rng.randint(margin, max(margin, limit))`
    fuer x und y. Rotierte Groesse via `_estimate_rotated_size()` fuer Grenzberechnung.
  - `"region"`-Feld traegt jetzt den echten Wert (`"top_left"`, `"free"` etc.)
    statt `"header_overlay"`.

**Annotation JSON**
- `box_annotations[*].region` traegt den tatsaechlichen Wert, nicht `"header_overlay"`.
- Neues Top-Level-Feld `"placement_mode": str` in `run_metadata` und `render_metadata`.

**Akzeptanzkriterien**
- Gleicher Seed + gleicher Modus → gleiche Positionen.
- Alle vier Ecken sind durch Seed-Variation erreichbar.
- Ordnername enthaelt den Modus-String.
- Keine Corner-Koordinaten ausserhalb der Bildgrenzen.

---

#### C — Annotiertes Preview mit roten Bounding Boxes

**`view.py`**
- Neue private Funktion `_draw_red_bounding_boxes(axis, annotations)`: identisch zu
  `_draw_annotation_outlines()`, aber `color="red"`, `linewidth=2.0`.
- Neue public Funktion `create_annotated_preview(dicom_path, box_annotations, output_path,
  title=None) -> Path`: liest den **injizierten** DICOM, extrahiert Frame, zeichnet rote Boxen,
  speichert mit `figsize=(8, 8)`, `dpi=150`. Kein `plt.show()`.

**`inject.py`**
- `create_annotated_preview` importieren.
- Neuer Output-Pfad: `run_dir / "preview_annotated.png"`.
- Nach `save_dicom()` aufrufen mit injiziertem DICOM und `pixel_result["box_annotations"]`.
- `"annotated_preview_file"` in den Record aufnehmen.

**Annotation JSON**
- Neues Top-Level-Feld `"annotated_preview_file": str` in `ground_truth.jsonl`
  und `run_manifest.json`.

**Akzeptanzkriterien**
- Run-Ordner enthaelt `preview.png` (unveraendert, lime) **und** `preview_annotated.png` (neu, rot).
- Rotierte Annotationen → rotierte Quadrilaterale, keine achsenparallelen Rechtecke.
- Leere `box_annotations` → valides PNG ohne Crash.
- `ground_truth.jsonl` und `run_manifest.json` enthalten `"annotated_preview_file"`.

---

**Aenderungen nach Datei**

| Datei | Feature | Was aendert sich |
|---|---|---|
| `inject.py` | A, B, C | CLI-Args, Call-Chain, Record, Run-ID-Format, Import |
| `pixel_injection.py` | A, B | Font-Aufloesung, Placement-Logik, RNG-Kapselung |
| `view.py` | C | `_draw_red_bounding_boxes`, `create_annotated_preview` |

### 1. Prototype-Stand sauber einfrieren — ERLEDIGT

- README beschreibt den aktuellen Ist-Stand einschliesslich aller neuen Parameter
- Alle fuenf injizierten Tags sind dokumentiert
- Wiederverwendbarkeits-Tabelle unterscheidet Prototype-Only von potenziell uebertragbaren Teilen
- Seed-Strategie und Reproduzierbarkeitsgarantie sind beschrieben

**Akzeptanznahe Outputs — erfuellt**

- Input, Output und Seed-Verhalten sind beschrieben
- Ist-Stand und beschlossener MVP sind dokumentiert
- `pixel_injection.py` als partiell uebertragbar (Rendering-Primitives) benannt

### 2. MVP fuer sichtbare Pixel-Injektion festziehen — ERLEDIGT

- `PatientName`, `PatientID`, `AccessionNumber` werden sichtbar gerendert
- `PatientBirthDate`, `PatientSex` bleiben tag-only
- Tag-Injektion und sichtbarer Overlay laufen gemeinsam in einem Run
- Sichtbare PHI wird nur in Frame `0` geschrieben, `frame_index: 0` in `box_annotations`

**Akzeptanznahe Outputs — erfuellt**

### 3. Platzierung und Rotation begrenzt, aber reproduzierbar machen — ERLEDIGT

- Diskrete Rotationsmenge: `(0, 20, 90, 180, 270)` — via `ALLOWED_ROTATIONS_DEGREES`
- `--placement-mode corners`: seed-gesteuert eine von vier Ecken; alle Annotationen in derselben Ecke
- `--placement-mode free`: unabhaengige Zufallsposition je Annotation, seed-gesteuert
- `random.Random(seed)` als lokale Instanz — kein globales State
- Gleicher Seed + gleiche Args → identische Positionen und Winkel

**Akzeptanznahe Outputs — erfuellt**

### 4. Ground-Truth-Artefakt auf proto-stabilen MVP-Stand bringen — ERLEDIGT

- Schema-Version `0.2.0-prototype`; `box_annotations` und `dicom_tag_annotations` getrennt
- Jede sichtbare Annotation enthaelt `label`, `text`, `region`, `corners` (4 `{x,y}`-Punkte),
  `rotation_degrees`, `frame_index`, `font_size_pct`
- `run_metadata` und `render_metadata` als eigene Top-Level-Objekte
- `annotated_preview_file` als Top-Level-Feld fuer visuell pruefbares Artefakt
- `preview_annotated.png` als manuell pruefbares Kontrollartefakt mit roten Bounding Boxes

**Akzeptanznahe Outputs — erfuellt**

**Noch offen:** Formales Schema-Dokument existiert noch nicht (siehe Paket 5)

### 5. Vereinheitlichtes Annotationsschema entwerfen

- Ein prototypisches, formatuebergreifendes Schema definieren, das drei Arten von Annotationen
  sauber unterscheiden kann:
  - `span_annotations` fuer Text, CSV, Dateinamen, Ordnernamen und andere inline markierte Inhalte
  - `box_annotations` fuer sichtbare PHI in bildbasierten DICOM-/PDF-Artefakten mit `corners` und
    `region`
  - `dicom_tag_annotations` fuer reine DICOM-Tag-Injektionen ohne 2D-Koordinaten
- Das Schema an den bereits beobachteten Datenmustern ausrichten:
  - Inline-Tags wie `<PER>...</PER>`, `<DATE>...</DATE>`, `<AGE>...</AGE>`
  - Sidecar-CSV oder vergleichbare Box-Daten mit `field`, `text`, `region`, Geometrie
  - aktuelles Prototype-`ground_truth.jsonl` fuer DICOM-Tag-Injektionen

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
  DICOM-Tag-Injektion
- Reine DICOM-Tag-Injektionen bleiben ueber Tag-Metadaten adressiert, nicht ueber 2D-Koordinaten
- Fuer den Prototype sollen Bounding Boxes so genau wie praktikabel erfasst werden; `corners` ist
  die Standardform fuer sichtbare Annotationen, besonders bei Rotation
- Das Schema ist proto-stabil: stark genug fuer weitere Prototype-Schritte und
  Phase-2-Vorbereitung, aber noch kein finaler Vertrag fuer `src/injection_pipeline/models/`

**Akzeptanznahe Outputs**

- Es gibt ein JSON-kompatibles Prototype-Schema oder einen gleichwertigen Modellvorschlag
- Das bestehende tag-basierte `ground_truth.jsonl` laesst sich nachvollziehbar auf das neue Schema
  abbilden
- Die Trennung zwischen Prototype-Schema und spaeterem produktionsreifem Modell in `src/` bleibt
  explizit

### 6. Output-Struktur pro Injektionslauf standardisieren — ERLEDIGT

- Benennung: `seed{:04d}-angle{:03d}-{mode}-{type}-{short_id}`
- Fuenf Artefakte pro Run-Ordner: injiziertes DICOM, `preview.png`, `preview_annotated.png`,
  `ground_truth.jsonl`, `run_manifest.json`
- Alle Pfade werden in `ground_truth.jsonl` als absolute Strings gespeichert

**Akzeptanznahe Outputs — erfuellt**

**Hinweis:** Aeltere Runs im `output/`-Ordner verwenden das alte Namensschema ohne
Platzierungsmodus-Segment — diese sind Legacy und werden nicht umbenannt.

### 7. Anschluss an Phase 2 vorbereiten — OFFEN

- Herausarbeiten, welche Prototype-Erkenntnisse spaeter in das abstrakte Dokument- und
  Annotationsmodell einfliessen sollen
- Offene Punkte markieren, die vor einer Uebernahme in `src/` entschieden werden muessen
- Explizit festhalten, dass Echo-/US-Heuristiken, aktuelle Positionsszenarien und
  Prototype-Orchestrierung nicht automatisch in `src/` uebernommen werden

**Akzeptanznahe Outputs**

- Es gibt eine Liste uebernehmbarer Prototype-Erkenntnisse
- Es gibt eine Liste offener Architekturentscheidungen fuer Phase 2 und Phase 3
- Prototype-spezifische Entscheidungen und uebertragbare Prinzipien sind getrennt aufgefuehrt

## Akzeptanzkriterien

- Diese Datei ist der eindeutige Arbeitsplan fuer den aktuellen DICOM-Prototyp
- Der Root-`PLAN.md` verweist auf diese Datei, ohne operative Prototype-Aufgaben selbst zu tragen
- Das geplante Annotationsschema deckt explizit Inline-/Span-Annotationen,
  Bounding-Box-Annotationen und DICOM-Tag-Annotationen ab
- Pixel-Injektion, variable Platzierung, Rotation und run-basierte Output-Ordner sind als
  konkrete Arbeitspakete beschrieben
- Der beschlossene MVP ist explizit dokumentiert:
  sichtbare `PatientName`-/`PatientID`-/`AccessionNumber`-Overlays, `PatientBirthDate` und
  `PatientSex` nur als Tags, Standardmodus mit Tag plus Overlay, Echo-/US-Only, kleine diskrete
  Rotationsmenge, `corners`, proto-stabiles Schema und Preview pro Run
- Die Trennung zwischen Prototype-Design und produktionsreifer Implementierung in `src/` bleibt klar

## Annahmen

- Der Scope dieser Datei umfasst nur den aktuellen DICOM-Prototyp
- Das vereinheitlichte Annotationsschema wird zunaechst als Prototype-/Design-Artefakt geplant
- Eine spaetere produktive Modellierung in `src/injection_pipeline/models/` erfolgt erst nach
  gesonderter Architekturentscheidung
