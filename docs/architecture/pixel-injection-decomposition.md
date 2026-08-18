# Zerlegung von `pixel_injection.py` und Abbau der Typing-Schulden (WP-E)

Status: Kernzerlegung am 2026-07-12 abgeschlossen. Zwei nicht blockierende
Punkte bleiben: Typisierung der internen Renderer-Payloads und die Entscheidung
zum Kompatibilitäts-Shim.

## Kernergebnis: Die Typing-Schulden sind kleiner als behauptet

Das TODO in `pyproject.toml` sagt, dass die Typisierung auf „das Dokumentmodell
als Ersatz für Dict-Payloads“ (Phase 2) wartet. Die gemessene Realität: Striktes
mypy auf dem Modul erzeugt *ohne* den Override **genau 13 Fehler, von denen
keiner die Dict-Payloads betrifft**. Alle 13 sind heute behebbare
PIL-/numpy-Typisierungsprobleme, ohne Änderung der Bytes und ohne WP-B. Der
Override kann *vor* der Zerlegung oder dem Domainmodell entfernt werden.
(Verifiziert am 2026-07-06 mit dem mypy des Repositories gegen `main`.)

## Implementierungsstatus, 2026-07-12

Implementiert:

- `pyproject.toml` enthält keinen `tool.mypy.overrides`-Block für die Engine mehr.
- Die Zuständigkeiten der Engine liegen in `frames.py`, `fonts.py`, `geometry.py`,
  `segments.py`, `overlay.py`, `handwriting.py`, `placement.py` und
  `injector.py`.
- `pixel_injection.py` exportiert die Legacy-Oberfläche aus Kompatibilitätsgründen
  erneut.
- `_write_pixel_array` liegt in `writers/dicom.py`.
- Die toten öffentlichen Hilfsfunktionen `build_visible_text_annotations` und
  `render_annotations_for_dataset` sind entfernt.

Offen:

- `dict[str, Any]`-Renderer-Payloads bleiben an einigen internen Engine-Grenzen;
  ihre Ersetzung durch kleinere interne Modelle kann auf eine
  verhaltensneutrale Bereinigung warten.

## Inventar der Typing-Schulden (vollständig)

| # | Zeile(n) | Fehlercode | Ursache | Korrektur (verhaltensneutral) |
|---|---|---|---|---|
| 1 | 44, 48 | `no-any-return` | `pixel_array[0]` / `pixel_array` gibt nach dem ndarray-Indexing in `extract_preview_frame` `Any` zurück | Rückgaben in `np.asarray(...)` einschließen (bereits das Eingabeidiom in Zeile 42) |
| 2 | 65 | `no-any-return` | `np.clip(...).astype(np.uint8)` wird in `normalize_to_uint8` als `Any` abgeleitet | Zwischenwert als `npt.NDArray[np.uint8]` annotieren oder in `np.asarray(..., dtype=np.uint8)` einschließen |
| 3 | 546, 562, 572, 573 | `arg-type` | `Image.new("...", (base_width, base_height))` — Größen werden als `int \| float` abgeleitet, weil `font.getbbox`-Stubs Floats zurückgeben und `max(1, right - left)` sie weiterträgt (`_prepare_annotation_overlay`) | Einmal an der Quelle umwandeln: `text_width = max(1, int(right - left))`, `text_height = max(1, int(bottom - top))` (Zeilen 540–541); beide Schriftklassen liefern bereits ganzzahlige Werte |
| 4 | 587, 588, 589, 591, 662, 663 | `attr-defined` | `Image.BICUBIC` — aus den Pillow-Stubs entfernt; Laufzeitalias von `Image.Resampling.BICUBIC` | Alle sechs Vorkommen durch `Image.Resampling.BICUBIC` ersetzen (identischer Enum-Wert; Resampling-Ausgabe unverändert) |

Die Entfernung besteht aus einem Patch für drei Zeilencluster plus dem Löschen
des `[[tool.mypy.overrides]]`-Blocks. Eine Regression-Sicherung ergänzt: Die CI
schlägt fehl, wenn ein neuer modulbezogener Override erscheint.

Hinweis zu Korrektur 3: `text_origin = (padding - left, padding - top)
(Zeile 544)` wird aus derselben Quelle ebenfalls als Float typisiert; PIL
akzeptiert Float-Textursprünge und mypy markiert dies nicht — die Umwandlung von
`left/top` in `int` an derselben Stelle erhält die Ursprungsarithmetik exakt wie
heute (getbbox liefert für TrueType-Schriften bei ganzzahligen Größen ganze
Zahlen; Assertion-Cast statt Rundung, damit ein künftiger nicht ganzzahliger
Fall sichtbar fehlschlägt).

## Aktuelles Funktionsinventar → Modulaufteilung

Sechs Zuständigkeiten teilen sich heute die Datei. Vorgeschlagene Aufteilung
unter `engine/`:

| Neues Modul | Funktionen (aktuelle Zeile) | Zuständigkeit |
|---|---|---|
| `frames.py` | `extract_preview_frame` (41), `normalize_to_uint8` (53), `frame_to_image` (69), `save_preview_image` (186) | Frame-Extraktion und Bildkonvertierung |
| `fonts.py` | `_FONT_PATHS` (19), `load_default_font` (77), `_resolve_font_size_px` (32), `_DEFAULT_FONT_SIZE_PX` (17) | Schriftauflösung (WP-C/config externalisiert Pfade später; ADR-0002) |
| `geometry.py` | `_validate_rotation` (853) + `ALLOWED_ROTATIONS_DEGREES` (15), `_coerce_position` (843), `_estimate_rotated_size` (788), `_rotated_corners` (865), `_mask_bounds_to_corners` (1048), `_thresholded_mask_bounds` (1086) + `_MASK_ALPHA_THRESHOLD` (28), `_require_mask_bounds` (1020), `_serialize_mask_bounds` (1031) | Mathematik für rotierte Ecken und Maskengrenzen |
| `segments.py` | `_normalize_text_segments` (907), `_draw_segment_masks` (935), `_split_prefix_and_pii_text` (984), `_resolve_segment_draw_bounds` (1002) | Verarbeitung von PII-/generischen Segmenten |
| `overlay.py` | `_prepare_annotation_overlay` (509), `_render_single_annotation` (388), `render_visible_annotations` (144) | Font-Text-Overlay-Rendering |
| `handwriting.py` | `_prepare_handwriting_asset_overlay` (648), `_render_handwriting_annotation` (453) | Handschrift-Asset-Overlay-Rendering |
| `placement.py` | `_materialize_positions` (707), `_VALID_PLACEMENT_MODES` (18) | geseedete Positionsauswahl |
| `injector.py` | `inject_visible_text` (196), `inject_visible_text_into_image` (243), `_inject_visible_text_into_frame` (280), `_render_frame_with_annotations` (488), `_build_box_annotation` (1067), `_TEXT_BACKGROUND_COLORS` (25) | Orchestrierungsfassade, die der Runner aufruft |
| `writers/dicom.py` (aus der Engine verschieben) | `_write_pixel_array` (803) | DICOM-Pixel-Schreiben ist eine *Writer*-Zuständigkeit: Es schreibt Transfer-Syntax, photometrische Interpretation und Frame-Metadaten um — Formatkonformität, nicht Rendering (entspricht ADR-0006; der DICOM-Writer besitzt die Datasetänderung zur Speicherung) |
| gelöscht | `build_visible_text_annotations` (99), `render_annotations_for_dataset` (169) | tote API, die die Präfixtaxonomie duplizierte |

Importsrichtung (keine Zyklen):
`injector → placement → overlay/handwriting → segments → geometry/fonts/frames`.
`overlay` und `handwriting` hängen beide von `geometry` + `segments` ab;
`placement` ruft zur Größenbestimmung `overlay._prepare_annotation_overlay` auf.
Diese Querverbindung ist inhärent (die Platzierung muss gemäß dem Kommentar in
Zeile 703–706 messen, was das Rendering zeichnet) und bleibt explizit.

Gefahr einer zirkulären Abhängigkeit: `_prepare_annotation_overlay` verzweigt zu
`_prepare_handwriting_asset_overlay`, wenn `renderer_type == "handwriting_asset"`
(Zeile 516). Umkehren: Der *Aufrufer* (`_render_single_annotation`,
`_materialize_positions`) verzweigt anhand von `renderer_type` in das passende
Modul, sodass `overlay` `handwriting` nie importiert. Das Verhalten bleibt
identisch — die Verzweigung erfolgt einen Frame früher.

## Reihenfolge

1. **Zuerst den Override entfernen** (unabhängig von allem): die 13 Korrekturen
   anwenden, den `pyproject.toml`-Block löschen und den Byte-Identitäts-Harness
   (WP-D, Schritt 0) ausführen — Resampling-Enum und Int-Umwandlungen dürfen
   kein Pixel ändern.
2. `geometry.py` + `fonts.py` + `frames.py` verschieben (Blattmodule ohne
   Abhängige im Repository außer der Engine selbst); Re-Exports in
   `pixel_injection.py` beibehalten.
3. `segments.py` und danach `overlay.py` + `handwriting.py` (mit der Umkehrung
   der Verzweigung) verschieben, anschließend `placement.py`.
4. Die Fassade nach `injector.py` verschieben; `pixel_injection.py` wird ein
   Re-Export-Shim; Imports in
   `tests/unit/test_pixel_injection_corners.py:14-21` und
   `tests/unit/test_handwriting_asset_rendering.py:8-11` aktualisieren; den
   Shim löschen, sobald `engine/__init__.py` die öffentliche Oberfläche exportiert.
5. `_write_pixel_array` bei Umsetzung von WP-F in den DICOM-Writer verschieben
   (dies ist neben der Fassade die einzige Engine-Funktion, die pydicom-
   Datasets berührt).
6. Die tote API (`build_visible_text_annotations`,
   `render_annotations_for_dataset`) und ihre `engine/__init__.py`-Exports
   löschen.

Jeder Schritt: pytest erfolgreich plus Byte-Identitäts-Harness. Schritte 1–4
benötigen keine WP-B-Typen; sobald WP-B umgesetzt ist, werden `dict[str, Any]`-
Parameter
(`annotation`, `visible_injections`, Overlay-Payload) zu
`RenderPlanItem` / `PlacedRenderItem` / `RenderedAnnotation` aufwerten — das
Overlay-Payload-Dict (Zeilen 595–642) ist der beste Kandidat für ein kleines
internes `OverlaySpec`-Modell, da es die Overlay-→Render-Grenze überschreitet.

## Gewinn für die Testbarkeit

- `geometry.py` und `segments.py` werden Module mit reinen Funktionen —
  Property-Tests (Eckenreihenfolge bei allen fünf Rotationen,
  Segmentrekonstruktion) werden trivial.
- `placement.py` isoliert den einzigen RNG-Konsumenten der Engine, wodurch die
  WP-G-Änderung zum „named stream“ auf ein Modul begrenzt wird.
- `injector.py` ist das einzige Modul, das der Runner (später: die Adapter)
  importieren darf.

## Implementierungsstatus

### Implementiert am 2026-07-12

- Typisierungskorrekturen wurden übernommen und der mypy-Override gelöscht.
- Engine-Module wurden in der oben genannten Reihenfolge aufgeteilt;
  `pixel_injection.py` bleibt als Kompatibilitäts-Export-Shim bestehen.
- Die Handschrift-Verzweigung erzeugt keinen Import von `overlay` nach
  `handwriting` mehr.
- Tote öffentliche Hilfsfunktionen wurden nach einer repositoryweiten
  Referenzprüfung entfernt.
- `_write_pixel_array` wurde während WP-F in den DICOM-Writer verschoben.

### Verbleibend

- Interne Renderer-Payloads verwenden an einigen Engine-Grenzen weiterhin
  `dict[str, Any]`.
- Das Beibehalten oder Löschen des Kompatibilitäts-Shims `pixel_injection.py`
  benötigt eine spätere Kompatibilitätsentscheidung.

Abschlusskriterium: Striktes mypy läuft ohne modulbezogene Overrides, die Engine
besitzt zusammenhängende Module und der eingecheckte E2E-Harness deckt
byte-stabile DCM/JPG-Ausgabe ab.
