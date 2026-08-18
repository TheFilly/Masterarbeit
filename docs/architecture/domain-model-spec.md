# Kanonisches Domain- und Ground-Truth-Schema-Design (WP-B)

Status: für die DICOM/JPG-Kernkette implementiert und auf den PDF-Sidecar
erweitert, aktualisiert am 2026-07-14. Implementiert ADR-0005 und die gemeinsame
ADR-0008-Versionslinie (`0.2.0-prototype`-Run-Records und
`0.3.0-pdf-prototype`-Sidecars).

Quelle der Wahrheit für das aktuelle Verhalten: `ground_truth.build_record()`,
die Planungsfunktionen in `planning.py`, der Aufbau der Annotationen in
`engine/injector.py`, die Modelle unter `models/` und die dokumentierte
Artefaktoberfläche in `docs/dicom-injection.md`.

## Design-Constraints

1. **Bytekompatibilität zuerst.** `model_dump(mode="json")` des neuen
   `RunRecord` muss für die eingefrorenen Validierungs-Runs die heutige
   `ground_truth.json` Byte für Byte reproduzieren (Schlüsselreihenfolge,
   `null`s, Float-Formatierung). Die Schlüsselreihenfolge in JSON folgt der
   Deklarationsreihenfolge der pydantic-Felder — Felder exakt in der aktuellen
   Ausgabereihenfolge deklarieren.
2. **`_make_json_safe` wird überflüssig.** `Path`-typisierte Felder werden
   nativ als Strings serialisiert; Tupel werden zu `list[...]`-typisierten
   Feldern. Kein eigener Shim.
3. **Taxonomieagnostisch.** Kein Modell hardcodiert Feldnamen wie
   `patient_name`; Identitäts-Payloads werden dynamisch verschlüsselt und beim
   Laden gegen das WP-C-Identifier-Schema validiert, nicht durch die
   Modellstruktur.
4. **Eine Hierarchie für alle Formate.** DCM, JPG und PDF verwenden dieselben
   Annotations- und Record-Modelle; formatspezifische Daten liegen in klar
   markierten optionalen Teilstrukturen.

## Modellbaum

```text
models/
├── geometry.py     ImagePoint, PdfPoint, Quad, MaskBounds
├── segments.py     TextSegment
├── identity.py     Identity
├── annotations.py  BoxAnnotation, DicomTagAnnotation, SpanAnnotation
├── rendering.py    RenderPlanItem, HandwritingAssetRef, RenderedAnnotation,
│                   AnnotationRenderDetail, EngineRenderMetadata
├── dicom.py        DicomContext
├── record.py       RunMetadata, RecordRenderMetadata, RunRecord
└── adapters.py     SourceDocument, InjectedDocument, WrittenArtifacts (WP-F)
```

Alle Modelle: `model_config = ConfigDict(extra="forbid"), sofern nicht anders angegeben.

## Implementierungsstatus, 2026-07-12

Implementiert:

- `models/geometry.py`, `segments.py`, `identity.py`, `annotations.py`,
  `dicom.py`, `rendering.py`, `record.py` und `adapters.py`.
- `ground_truth.build_record()` erzeugt ein validiertes `RunRecord`; das
  Schreiben der JSON-Artefakte verwendet `model_dump(mode="json")`.
- `load_run_record()` akzeptiert `0.2.0-prototype` und weist unbekannte Versionen zurück.
- Unit- und E2E-Tests decken Modell-Validatoren, Record-Round-Trip-Verhalten und
  Byte-Hashes der DCM/JPG-Artefakte ab.

Offen:

- Künftige ausgegebene DICOM/JPG-Schema-Versionen und ihre ADR-0008-Changelog-
  Einträge.
- Identifier-Schema-Provenienz und Reproduzierbarkeits-/Umgebungsfelder im
  ausgegebenen Record.
- Breitere PDF-Sidecar-Integrations-Fixtures und künftige Provenienzfelder.

### Geometrie (`models/geometry.py`)

| Modell | Felder | Validierung |
|---|---|---|
| `ImagePoint` | `x: float`, `y: float` | Ursprung oben links, Pixel. Serialisiert als `{"x": ..., "y": ...}`; entspricht der Ausgabe von `engine.geometry._rotated_corners()`. |
| `PdfPoint` | `x: float`, `y: float` | Ursprung unten links, PDF-Punkte. Eigenständiger Typ gemäß PDF-Plan („Sidecar Schema Direction“) — nie mit `ImagePoint` austauschbar. |
| `Quad` | `list[ImagePoint]` (annotierter Typ oder RootModel) | Genau 4 Punkte, Reihenfolge der Ecken erhalten (vor der Rotation oben links, oben rechts, unten rechts, unten links). |
| `MaskBounds` | `left: int`, `top: int`, `right: int`, `bottom: int`, `width: int`, `height: int` | `width == right - left`, `height == bottom - top` (Modell-Validator). |

### Textsegmente (`models/segments.py`)

`TextSegment`: `kind: Literal["generic", "pii"]`, `text: str`. List-level
Validierung (verwendet von `RenderPlanItem`): Die zusammengefügten Segmenttexte
ergeben den vollständigen gerenderten Text, und mindestens ein nicht leeres
`pii`-Segment ist vorhanden. Das Modell besitzt diese Normalisierung und
Validierung.

### Identität (`models/identity.py`)

```python
Identity:
    identity_id: str          # selected by identifier_schema.identity_id_field
    seed: int                 # der Seed, der ihn erzeugt hat
    fields: dict[str, str]    # Feldname -> Wert, Schlüssel aus dem Identifier-Schema
```

Begründung: Eine attributfeste `Identity(patient_name=..., ...)` würde die von
WP-C externalisierte Taxonomie erneut hardcodieren. Das Identifier-Schema (WP-C)
validiert, welche Schlüssel vorhanden sein müssen; das Modell garantiert nur
die Form. `identity_id` bleibt ein einfacher String, dessen *Ableitung* (heute:
das Feld `patient_id`) eine Regel auf Schemaebene
(`identity_id_field` im WP-C-Schema) und keine Modellregel ist.

### Annotationen (`models/annotations.py`)

`BoxAnnotation` — eine sichtbar gerenderte PII-Box, erzeugt durch
`engine.injector._build_box_annotation()`:

| Feld | Typ | Heutiger Schlüssel |
|---|---|---|
| `label` | `str` | `label` |
| `text` | `str` | `text` (nur der PII-Teil) |
| `rendered_text` | `str` | `rendered_text` (Präfix + PII) |
| `region` | `str` | `region` (`top_left` \| `top_right` \| `bottom_left` \| `bottom_right` \| `free`; `str` beibehalten, Werte kommen aus der Platzierung) |
| `corners` | `Quad` | `corners` |
| `label_corners` | `Quad \| None` | `label_corners` (`null` ohne Präfix) |
| `rotation_degrees` | `int` | `rotation_degrees` |
| `frame_index` | `int` | `frame_index` (heute immer 0) |
| `font_size_pct` | `int` | `font_size_pct` |

`DicomTagAnnotation` — ein injiziertes DICOM-Tag, erzeugt durch
`planning.build_tag_annotations()`:

| Feld | Typ | Heutiger Schlüssel |
|---|---|---|
| `label` | `str` | `label` |
| `tag_address` | `str` | `tag_address` (Form `"0010,0010"`; per Regex `^[0-9A-F]{4},[0-9A-F]{4}$` validieren) |
| `tag_keyword` | `str` | `tag_keyword` |
| `dicom_vr` | `str` | `dicom_vr` (2 Großbuchstaben) |
| `value` | `str` | `value` |
| `identity_field` | `str` | `identity_field` |
| `identity_id` | `str` | `identity_id` |
| `source_file` | `Path` | `source_file` (serializes to string) |
| `output_file` | `Path` | `output_file` |

`SpanAnnotation` — für Textspan-Formate reserviert (wird derzeit von
`ground_truth.build_record()` als `[]` ausgegeben). Aktuell minimal:
`label: str`, `text: str`, `start: int`, `end: int`, `identity_field: str`.
Vorläufig; PLAN.md Phase 2 besitzt das endgültige Design.

### Rendering (`models/rendering.py`)

`RenderPlanItem` — Ausgabe des Planners und Eingabe der Engine, erzeugt durch
`planning.build_visible_render_plan()` und optional erweitert durch
`engine.handwriting_manifest.apply_handwriting_assets()`:

- `label: str`, `text: str`, `text_segments: list[TextSegment]`,
  `identity_field: str`, `region: str`, `rotation_degrees: int`,
  `line_index: int`
- `renderer_type: Literal["font_text", "handwriting_asset"] = "font_text"`
- `asset_id: str | None = None`, `asset: HandwritingAssetRef | None = None`
- Von der Engine ergänzte Platzierungsfelder (`position`, `padding`,
  `stroke_width`) gehören zu einem abgeleiteten `PlacedRenderItem`, nicht zum
  Plan-Element: Planung und Platzierung sind verschiedene Stufen mit
  unterschiedlichen Daten.

`HandwritingAssetRef` (normalisierter Manifesteintrag aus
`engine.handwriting_manifest.load_handwriting_manifest()`): `asset_id: str`,
`text: str`, `identity_field: str`, `ink_color: str | None`,
`background_mode: str | None`, `image_path: Path`, `mask_path: Path`.
`extra="allow"` — Manifeste enthalten generatorspezifische Schlüssel, die bis
in `render_metadata` erhalten bleiben müssen.

`AnnotationRenderDetail` — von der Engine erzeugtes `render_metadata` pro
Annotation:
`position: {x, y}` (Modell
`PixelPosition(x: int, y: int)`), Font-Felder (`font_family`, `font_name`,
`font_size`, `padding`, `fill_rgb: list[int]`, `stroke_fill_rgb`,
`stroke_width`, `background_enabled`, `background_color: list[int] | None`),
`text_segments: list[TextSegment]`, `geometry_source: str`,
`mask_coordinate_space: str`, `mask_alpha_threshold: int`,
`text_mask_bounds / pii_mask_bounds / label_mask_bounds: MaskBounds | None`,
`text_box_size / rotated_box_size: {width, height}`,
`rendered_text_corners: Quad` und für Handschrift: `renderer_type`,
`asset_id`, `asset_path: Path`, `mask_path: Path`, `ink_color`,
`background_mode`. Font-Text und Handschrift geben unterschiedliche
Schlüsselmengen aus — als eine Klasse mit optionalen Feldern modellieren
(einfachste Bytekompatibilität) und eine diskriminierte Union erst nach
Lockerung der Bytekompatibilität prüfen. Handschrift zeichnet zusätzlich
`selected_ink_color`, `contrast_mode`, `sampled_luminance`, `luminance_spread`
und `contrast_decision_reason` auf; diese beschreiben das Erscheinungsbild zur
Renderzeit und ändern die Maskengeometrie nicht.

`RenderedAnnotation` — die von `engine/injector.py` erzeugten Einträge:
`label`, `text`, `rendered_text`,
`generic_text`, `pii_text`, `region`, `rotation_degrees`, `corners: Quad`,
`label_corners: Quad | None`, `render_metadata: AnnotationRenderDetail`.

`EngineRenderMetadata` — der von `engine/injector.py` zurückgegebene
Metadatenblock auf Engine-Ebene: `seed: int`, `rotation_degrees: int`,
`allowed_rotations_degrees: list[int]`, `frame_count: int`,
`applied_frame_indices: list[int]`, `effective_font_family: str`,
`effective_font_size_px: int`, `background_enabled: bool`,
`background_color: list[int] | None`, `geometry_source: str`,
`renderer_types: list[str]`, `handwriting_assets: list[...]` (id/paths/ink
subset), `geometry_notes: str`,
`mask_alpha_threshold: int`, `visible_annotations: list[RenderedAnnotation]`.
Handschrift-Runs können zusätzlich die angeforderten
`handwriting_ink_color` und `handwriting_contrast_mode` enthalten; diese Felder
werden bei reinen Font-Records weggelassen.

### DICOM-Kontext (`models/dicom.py`)

`DicomContext` (aus `summarize_dicom`, `loaders/dicom.py:20`): `modality`,
`sop_instance_uid`, `study_instance_uid`, `series_instance_uid` (alle
`str | None`), `rows`, `columns`, `samples_per_pixel` (`int | None`),
`photometric_interpretation: str | None`, `number_of_frames: int | None`,
`has_pixel_data: bool`. Hinweis: pydicom gibt nicht als String typisierte
Elemente (`PersonName`, `UID`) zurück; der Loader muss explizit in `str`
umwandeln — heute verarbeitet `json.dump` `UID`, weil es von `str` erbt, daher
ist die Umwandlung verhaltensneutral.

### Run-Record (`models/record.py`)

`RunMetadata` (Schlüssel in Ausgabereihenfolge, definiert in `models/record.py`):
`rotation_degrees: int`, `placement_mode: str`,
`pixel_injection_status: str`, `pixel_renderer: str`,
`visible_identity_fields: list[str]`, `tag_only_identity_fields: list[str]`,
`source_dicom_context: DicomContext | None = None`,
`output_dicom_context: DicomContext | None = None`.
Serialisierungsregel: Die beiden Kontextfelder werden bei **`None` weggelassen**
(JPG-Runs haben diese Schlüssel nicht; siehe
`ground_truth.attach_dicom_contexts()`); alles andere serialisiert `None` als
`null`. Mit einer auf diese beiden Felder begrenzten
`model_serializer`-/`exclude_none`-Behandlung implementieren.

`RecordRenderMetadata` (`models/record.py`): `rotation_degrees: int`,
`placement_mode: str`, `font_size_pct: int`, `font_family: str`,
`text_background: str | None`, `visible_render_plan: list[RenderPlanItem]`,
dann die abgeflachten Felder von `EngineRenderMetadata`. Für Bytekompatibilität
verteilt `ground_truth.build_record()` den validierten Engine-Block in dieses
Modell und *inline* die Felder von `EngineRenderMetadata` nach
`visible_render_plan` (Zusammensetzung über abgeflachte Serialisierung oder
direkte Feldduplizierung — die Implementierung kann wählen, die Byteausgabe ist
der Vertrag).

`RunRecord` (field order = emission order, `models/record.py`):

| Field | Type | Notes |
|---|---|---|
| `schema_version` | `str` | `"0.2.0-prototype"` emitted (ADR-0008) |
| `record_type` | `str` | `f"{document_type}_injection_run"` |
| `run_id` | `str` | |
| `seed` | `int` | |
| `rotation_degrees` | `int` | |
| `source_file` | `Path` | |
| `output_file` | `Path` | |
| `preview_file` | `Path` | akzeptiert den Preview-Pfad der Engine und serialisiert ihn als String |
| `annotated_preview_file` | `Path` | |
| `document_type` | `str` | heute `"dcm"` \| `"jpg"`; offene Menge für neue Formate |
| `example_type` | `str` | |
| `modality` | `str \| None` | `null` for JPG |
| `identity_id` | `str` | |
| `span_annotations` | `list[SpanAnnotation]` | heute `[]` |
| `box_annotations` | `list[BoxAnnotation]` | |
| `dicom_tag_annotations` | `list[DicomTagAnnotation]` | `[]` for JPG |
| `run_metadata` | `RunMetadata` | |
| `render_metadata` | `RecordRenderMetadata` | |

Jeder derzeit von `ground_truth.build_record()` geschriebene Schlüssel ist oben
berücksichtigt. Die pydantic-Serialisierung verarbeitet Pfade und verschachtelte
typisierte Metadaten.

## Versionierung (mit ADR-0008)

- Eine Versionslinie, dokumentiert in einer vom Implementierer begonnenen
  `docs/architecture/schema-changelog.md`:
  - `0.2.0-prototype` — aktuelles Run-Record (Bytekompatibilitätsziel dieser
    Spezifikation).
  - `0.3.0-pdf-prototype` — PDF-Sidecar für den PDF-Loader/Writer-Pfad; seine
    Punkt-/Quad-Modelle kommen aus `models/geometry.py`.
  - `0.4.0` — erste von den pydantic-Modellen ausgegebene Version, sobald die
    Bytekompatibilität mit `0.2.0-prototype` bewusst beendet wird (künftiges
    ADR; nicht Teil dieses Pakets).
- `load_run_record(path)` validiert derzeit nur DICOM/JPG-`RunRecord`-Artefakte
  mit `0.2.0-prototype`. Der `0.3.0-pdf-prototype`-Sidecar wird vom PDF-Pfad
  direkt mit `PdfAnnotationRecord.model_validate_json()` validiert und nicht
  über `load_run_record()` verteilt. Versionsspezifische Golden Fixtures unter
  `tests/fixtures/schemas/` bleiben für weitere veröffentlichte Versionen eine
  künftige Anforderung. Alte `ground_truth.json`-Dateien bleiben dauerhaft
  einlesbar, oder ihre Version wird durch ein ADR ausdrücklich verworfen.
- Additive Änderung = MINOR-Erhöhung plus neue Golden File. Nicht
  rückwärtskompatible Änderung = MAJOR (oder vor 1.0: MINOR mit Migrationsnotiz)
  plus ADR.

## Hinweise zur Byte-Kompatibilität (Golden-Test-Checkliste)

- `json.dump(record, indent=2)` plus abschließendes `"\n"` für
  `ground_truth.json`; kein abschließender Zeilenumbruch für
  `run_manifest.json` (`ground_truth.write_run_artifacts()`, ADR-0004).
- Eckkoordinaten sind `round(value, 2)`-Floats — `100.0` muss als `100.0`, nicht
  als `100` ausgegeben werden; Felder als `float` beibehalten, nie in `int`
  umwandeln.
- `label_corners`/`label_mask_bounds` geben bei Abwesenheit `null` aus (nicht
  weglassen).
- `run_metadata.source_dicom_context`/`output_dicom_context` werden bei JPG-Runs
  *weggelassen* (nicht als `null` ausgegeben).
- Handschrift-Asset-Einträge in `visible_render_plan` enthalten die vollständige
  normalisierte Asset-Zuordnung einschließlich absoluter Pfade (heute durch
  `_make_json_safe` in Strings umgewandelt); `HandwritingAssetRef` mit
  `Path`-Feldern reproduziert dies.
- Der Fallback für den Schriftnamen `"PillowDefaultFont"`
  (`engine/overlay.py`) ist Teil der Oberfläche.

## Annotiertes Beispiel (gekürzter DCM-Run)

```jsonc
{
  "schema_version": "0.2.0-prototype",        // RunRecord.schema_version
  "record_type": "dcm_injection_run",         // RunRecord.record_type
  "run_id": "dcm-27052026-1435-seed0042-angle020-corners-fs100-arial-none",
  "seed": 42,
  "rotation_degrees": 20,
  "source_file": "DicomData/Dicom-Files/91180014_0001.dcm",   // Path -> str
  "output_file": "output/dcm-.../91180014_0001_injected.dcm",
  "preview_file": "output/dcm-.../preview.png",
  "annotated_preview_file": "output/dcm-.../preview_annotated.png",
  "document_type": "dcm",
  "example_type": "dicom-files",
  "modality": "US",                            // null for JPG runs
  "identity_id": "SYNTH-661414",
  "span_annotations": [],                      // list[SpanAnnotation]
  "box_annotations": [
    {
      "label": "PatientID",
      "text": "661414",                        // nur der PII-Teil
      "rendered_text": "SYNTH-661414",         // prefix + PII
      "region": "top_left",
      "corners": [ {"x": 74.13, "y": 30.0}, ... ],   // Quad of ImagePoint
      "label_corners": [ ... ],                // null ohne Präfix
      "rotation_degrees": 20,
      "frame_index": 0,
      "font_size_pct": 100
    }
  ],
  "dicom_tag_annotations": [
    {
      "label": "PatientName",
      "tag_address": "0010,0010",
      "tag_keyword": "PatientName",
      "dicom_vr": "PN",
      "value": "Smith^Anna",
      "identity_field": "patient_name",
      "identity_id": "SYNTH-661414",
      "source_file": "...", "output_file": "..."
    }
  ],
  "run_metadata": {
    "rotation_degrees": 20,
    "placement_mode": "corners",
    "pixel_injection_status": "rendered",
    "pixel_renderer": "pixel_injection.inject_visible_text",
    "visible_identity_fields": ["patient_name", "patient_id", "accession_number"],
    "tag_only_identity_fields": ["patient_birth_date", "patient_sex"],
    "source_dicom_context": { "modality": "US", ... },   // omitted for JPG
    "output_dicom_context": { ... }
  },
  "render_metadata": {
    "rotation_degrees": 20,
    "placement_mode": "corners",
    "font_size_pct": 100,
    "font_family": "arial",
    "text_background": null,
    "visible_render_plan": [ /* RenderPlanItem[] */ ],
    "seed": 42,                                // EngineRenderMetadata, flattened
    "allowed_rotations_degrees": [0, 20, 90, 180, 270],
    "frame_count": 47,
    "applied_frame_indices": [0],
    "effective_font_family": "arial",
    "effective_font_size_px": 18,
    "geometry_source": "mask_bbox_after_final_rotation",
    "mask_alpha_threshold": 8,
    "visible_annotations": [ /* RenderedAnnotation[] */ ]
  }
}
```

Die JPG-Variante unterscheidet sich genau wie in `docs/dicom-injection.md`:
`record_type = "jpg_injection_run"`, `document_type = "jpg"`,
`modality: null`, `dicom_tag_annotations: []`, no DICOM contexts in
`run_metadata`.

## Implementierungsstatus

### Implementiert am 2026-07-12

- Modellmodule erstellt und Validatoren durch Unit-Tests abgedeckt.
- `models/rendering.py` und `models/record.py` deklarieren die aktuelle
  Ausgabereihenfolge.
- E2E-Tests parsen `ground_truth.json` mit `load_run_record()` und prüfen die
  bytekompatible Serialisierung von `ground_truth.json` und `run_manifest.json`.
- Runner-/Engine-Ausgaben sind mit `BoxAnnotation`, `DicomTagAnnotation`,
  `DicomContext` und `RunRecord` verbunden; `_make_json_safe` wurde gelöscht.

### Verbleibend

- `docs/architecture/schema-changelog.md` dokumentiert die gemeinsame
  Versionslinie.
- Künftige DICOM/JPG-Provenienzfelder benötigen eine spätere additive
  Schemaerhöhung.

Abschlusskriterium: Der DICOM/JPG-`RunRecord`-Pfad ist implementiert und strikt
typgeprüft. ADR-0008 bleibt für künftige ausgegebene Versionen und PDF-Sidecar-
Records maßgeblich.
