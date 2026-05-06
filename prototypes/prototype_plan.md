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

## Ist-Stand

- Der aktuelle Prototyp injiziert reproduzierbar fuenf DICOM-Tags in genau eine Echo-DICOM-Datei
- Sichtbare Pixel-Injektion ist fuer `PatientName`, `PatientID` und `AccessionNumber` im
  Echo-/US-Beispiel umgesetzt
- `PatientBirthDate` und `PatientSex` bleiben tag-only
- Das Ground-Truth-Artefakt ist proto-stabil auf Run-Ebene und unterscheidet bereits zwischen
  `dicom_tag_annotations` und `box_annotations`
- `inject.py` ist weiterhin Quick-and-Dirty-Orchestrierung und wird nicht als Vorlage fuer die
  spaetere `src/`-Architektur betrachtet
- Wiederverwendbare Ideen liegen eher in Hilfslogik wie Identitaetsgenerierung oder DICOM-Schreiben,
  nicht in der aktuellen Ablaufstruktur

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

### 1. Prototype-Stand sauber einfrieren

- Den aktuellen Tag-Injektions-Stand in `prototypes/dicom/README.md` eindeutig als Ist-Stand
  festhalten
- Dokumentieren, dass heute genau diese fuenf Tags injiziert werden:
  `PatientName`, `PatientID`, `PatientBirthDate`, `PatientSex`, `AccessionNumber`
- Festhalten, dass sichtbare Pixel-Injektion noch aussteht und Teil des beschlossenen MVP ist
- Trennen, welche Teile prototypische Orchestrierung bleiben und welche Erkenntnisse spaeter in
  `src/` ueberfuehrt werden koennen

**Akzeptanznahe Outputs**

- Input, Output und Seed-Verhalten sind eindeutig beschrieben
- Ist-Stand und beschlossener MVP sind klar getrennt dokumentiert
- Prototype-Only-Teile und potenziell uebertragbare Erkenntnisse sind benannt

### 2. MVP fuer sichtbare Pixel-Injektion festziehen

- Den Prototyp von reiner DICOM-Tag-Injektion auf sichtbare Injektion im Pixelraum erweitern
- Als sichtbare MVP-Identifier ausschliesslich `PatientName`, `PatientID` und
  `AccessionNumber` rendern
- `PatientBirthDate` und `PatientSex` im MVP nur als DICOM-Tag injizieren
- Standardmodus so vorbereiten, dass sichtbarer Overlay-Text und DICOM-Tag-Injektion gemeinsam
  stattfinden

**Akzeptanznahe Outputs**

- Pro injiziertem Run ist klar, welche Identifier sichtbar sind und welche tag-only bleiben
- Der MVP bleibt zunaechst auf das Echo-/US-Beispiel begrenzt
- Die Dokumentation unterscheidet sauber zwischen MVP-Verhalten und spaeterer Generalisierung
- Sichtbare PHI wird im aktuellen Prototype bewusst nur fuer Frame `0` erzeugt und entsprechend
  annotiert

### 3. Platzierung und Rotation begrenzt, aber reproduzierbar machen

- Fuer das Echo-/US-Beispiel eine kleine Menge fester Platzierungsregionen definieren
- Rotation im MVP auf eine kleine diskrete Menge begrenzen; keine freie Rotation und keine dichte
  Winkelabdeckung
- Seed-gesteuerte Auswahl von Position und Rotationsvariante festlegen
- Sicherstellen, dass Injektionen plausibel in headernahen oder overlay-typischen Bereichen liegen,
  ohne den Bildinhalt unbrauchbar zu machen
- In den Funktionsparametern den konkret verwendeten Winkel explizit fuehren

**Akzeptanznahe Outputs**

- Es gibt eine kleine, benannte Menge von Layout- und Positionsvarianten fuer das Echo-Beispiel
- Die diskrete Rotationsmenge ist dokumentiert und technisch fuehrbar
- Gleicher Seed und gleiche Quelle fuehren zu gleichem Layout und gleichem Winkel
- Die aktuellen diskreten Winkel muessen ohne Ueberlappung renderbar bleiben

### 4. Ground-Truth-Artefakt auf proto-stabilen MVP-Stand bringen

- Das aktuelle `ground_truth.jsonl` vom reinen Tag-Artefakt auf ein proto-stabiles MVP-Artefakt
  weiterentwickeln
- Pflichtmetadaten fuer Vergleichbarkeit zwischen Runs festziehen
- Sichtbare Injektionen als Pflichtbestandteil mit moeglichst genauer Geometrie aufnehmen
- `corners` als Standardform fuer sichtbare Annotationen verbindlich festlegen
- Regeln fuer rotierte sichtbare Injektionen dokumentieren, ohne bereits polygonale Freiformen als
  Muss einzufuehren

**Akzeptanznahe Outputs**

- Es gibt eine Soll-Ist-Liste fuer das aktuelle Prototype-`ground_truth.jsonl`
- Jedes sichtbare Overlay hat genau eine Annotation mit Text, Label, Region, `corners` und falls
  relevant `rotation_degrees`
- Falls sichtbare PHI nur auf einem Teil der Frames liegt, muss dies explizit ueber
  `frame_index` oder gleichwertige Metadaten nachvollziehbar sein
- Run-Metadaten reichen aus, um Artefakte spaeter reproduzierbar zu vergleichen

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

### 6. Output-Struktur pro Injektionslauf standardisieren

- Fuer jede Injektion oder jeden Prototype-Run einen eigenen Sub-Ordner unter `output/` erzeugen
- Den Sub-Ordner reproduzierbar benennen mit mindestens Seed, Winkel, Beispielart und kurzer ID
- Annotationen, injizierte DICOM-Datei und Preview gemeinsam in diesem Run-Ordner ablegen
- Preview als Standardartefakt behandeln, nicht als rein optionales Debug-Bild

**Akzeptanznahe Outputs**

- Es gibt eine Konvention fuer Run-spezifische Output-Pfade
- Die Benennung traegt Seed, Winkel, Beispielart und kurze ID
- Ein Run laesst sich allein ueber seinen Run-Ordner nachvollziehen
- Preview und Manifest muessen den tatsaechlich geschriebenen DICOM-Zustand widerspiegeln

### 7. Anschluss an Phase 2 vorbereiten

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
