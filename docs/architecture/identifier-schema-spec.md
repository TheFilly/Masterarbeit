# Externalisierung des Identifier-Schemas (WP-C)

Status: für die DICOM/JPG-Kernkette implementiert, aktualisiert am 2026-07-12.
Implementiert ADR-0007 für das Prototype-Schema. Die Ausgabe der
Schema-Provenienz bleibt durch ADR-0008 blockiert.

## Was als Taxonomie gilt (muss in Daten verschoben werden)

Alles, was beantwortet, „welche Felder existieren und was mit ihnen geschieht“:
Feldnamen, Generierungsrezepte, synthetische Präfixe, DICOM-Tag-Routing,
Routing sichtbar versus nur als Tag, Reihenfolge der Renderzeilen und Ableitung
der Identity-ID.

## Was im Code bleibt (Mechanismus, nicht Taxonomie)

Faker-Provider-Implementierungen, Rendering-Mechanik, Geometrie,
VR-bewusstes Tag-Schreiben, Masken-/Segmentmechanik und Datei-I/O. Das Schema
*benennt* ein Generierungsrezept; der Code implementiert es.

## Dateiformat und Speicherort

`configs/identifier_schemas/dicom-prototype.json` — JSON (entspricht der
Konfigurationsformat-Entscheidung des PDF-Plans; keine neue Abhängigkeit).
Wird von `config/identifier_schema.py` in pydantic-Modelle geladen (siehe unten).
Das aktive Schema wird über die CLI-Option `--identifier-schema` ausgewählt,
deren Standard das Prototype-File ist. Das Aufzeichnen des aufgelösten
Schema-Pfads sowie von `schema_id`/`version` in `run_metadata` bleibt eine
additive Nacharbeit und benötigt das Ausgabeversions-Gate aus ADR-0008.

## Struktur des Schemas

```jsonc
{
  "schema_id": "dicom-prototype",
  "version": "1.0.0",
  "description": "Die fünf Prototype-Felder, ohne Verhaltensänderung externalisiert.",
  "identity_id_field": "patient_id",        // Wert welches Feldes zu identity_id wird
  "generator": {
    "provider": "faker",
    "locale": "en_US",                       // heute in generator.py:9 hardcodiert
    "reference_date": "2026-07-10",          // festes Datum für datumsabhängige Faker-Rezepte
    "reference_date_policy": "faker-date_of_birth-reference-v1"
  },
  "fields": [ /* geordnete Liste — Reihenfolge ist Faker-Aufrufreihenfolge (siehe Determinismus) */ ]
}
```

Jeder Feldeintrag:

```jsonc
{
  "name": "patient_id",                      // Name des Identitätsfeldes (WP-B-Schlüssel Identity.fields)
  "category": "identifier",                  // freies Label für Berichte; Pipeline-Logik DARF nicht danach verzweigen
  "generation": {
    "recipe": "numerify",                    // benanntes Rezept, implementiert in identity/
    "arguments": { "text": "######" },
    "value_template": "SYNTH-{value}"        // prefix applied at generation time
  },
  "generic_prefix": "SYNTH-",                // segmentation rule for rendering (ADR-0003); null if none
  "routing": {
    "dicom_tag": {                           // null für nicht per DICOM adressierbare Felder
      "keyword": "PatientID",
      "address": "0010,0020",
      "vr": "LO"
    },
    "visible_pixel": { "enabled": true, "line_index": 1 }   // enabled:false = nur Tag
  }
}
```

Pydantic-Modelle in `config/identifier_schema.py` (alle `extra="forbid"`):
`IdentifierSchema`, `GeneratorConfig`, `FieldSpec`, `GenerationSpec`,
`DicomTagRoute`, `VisiblePixelRoute`. Validierung beim Laden: eindeutige
Feldnamen; `identity_id_field` ist vorhanden; `line_index`-Werte sind unter den
sichtbar aktivierten Feldern eindeutig und bilden `0..n-1`; `generic_prefix`
muss, wenn gesetzt, ein Präfix des literalen Anfangs von `value_template` sein
(damit die Segmentierung beim Rendern nie fehlschlägt); `address` entspricht
`^[0-9A-F]{4},[0-9A-F]{4}$`; `vr` besteht aus zwei Großbuchstaben;
`reference_date` ist ein ISO-Datum; `reference_date_policy` ist nicht leer.

## Ausgearbeitetes Beispiel: die heutigen fünf Felder als Daten

```jsonc
{
  "schema_id": "dicom-prototype",
  "version": "1.0.0",
  "identity_id_field": "patient_id",
  "generator": {
    "provider": "faker",
    "locale": "en_US",
    "reference_date": "2026-07-10",
    "reference_date_policy": "faker-date_of_birth-reference-v1"
  },
  "fields": [
    {
      "name": "patient_name",
      "category": "person_name",
      "generation": { "recipe": "dicom_person_name", "arguments": {}, "value_template": "{value}" },
      "generic_prefix": null,
      "routing": {
        "dicom_tag": { "keyword": "PatientName", "address": "0010,0010", "vr": "PN" },
        "visible_pixel": { "enabled": true, "line_index": 0 }
      }
    },
    {
      "name": "patient_id",
      "category": "identifier",
      "generation": { "recipe": "numerify", "arguments": { "text": "######" }, "value_template": "SYNTH-{value}" },
      "generic_prefix": "SYNTH-",
      "routing": {
        "dicom_tag": { "keyword": "PatientID", "address": "0010,0020", "vr": "LO" },
        "visible_pixel": { "enabled": true, "line_index": 1 }
      }
    },
    {
      "name": "patient_birth_date",
      "category": "date",
      "generation": { "recipe": "date_of_birth", "arguments": { "minimum_age": 18, "maximum_age": 90, "format": "%Y%m%d" }, "value_template": "{value}" },
      "generic_prefix": null,
      "routing": {
        "dicom_tag": { "keyword": "PatientBirthDate", "address": "0010,0030", "vr": "DA" },
        "visible_pixel": { "enabled": false, "line_index": null }
      }
    },
    {
      "name": "patient_sex",
      "category": "code",
      "generation": { "recipe": "random_element", "arguments": { "elements": ["M", "F"] }, "value_template": "{value}" },
      "generic_prefix": null,
      "routing": {
        "dicom_tag": { "keyword": "PatientSex", "address": "0010,0040", "vr": "CS" },
        "visible_pixel": { "enabled": false, "line_index": null }
      }
    },
    {
      "name": "accession_number",
      "category": "identifier",
      "generation": { "recipe": "numerify", "arguments": { "text": "#######" }, "value_template": "ACC-{value}" },
      "generic_prefix": "ACC-",
      "routing": {
        "dicom_tag": { "keyword": "AccessionNumber", "address": "0008,0050", "vr": "SH" },
        "visible_pixel": { "enabled": true, "line_index": 2 }
      }
    }
  ]
}
```

`dicom_person_name` ist ein benanntes Rezept (Code), das
`f"{last_name}^{first_name}"` erzeugt — die Verkettung mit `^` ist ein DICOM-
PN-Mechanismus und keine Taxonomie; sie bleibt daher als Rezeptimplementierung
in `identity/recipes.py`.

## Vorher-nachher-Abbildung

| Hardcodierte Konstante | Heutiger Ort | Ziel im Schema |
|---|---|---|
| `_TAG_META` (Keyword → Adresse, VR) | `runner.py:27-33` | `fields[*].routing.dicom_tag.{address,vr}` |
| `_IDENTITY_FIELD_MAP` (Keyword → Feldname) | `runner.py:35-41` | implizit: `fields[*].name` + `routing.dicom_tag.keyword` (ein Eintrag, zwei Ansichten) |
| `_VISIBLE_PIXEL_KEYWORDS` + Reihenfolge | `runner.py:43-47`, Reihenfolge über `enumerate` bei `:348` | `fields[*].routing.visible_pixel.{enabled,line_index}` |
| `_TAG_ONLY_KEYWORDS` | `runner.py:48` | `visible_pixel.enabled: false` |
| `SYNTH-`-Präfixgenerierung | `identity/generator.py:15` | `patient_id.generation.value_template` |
| `ACC-`-Präfixgenerierung | `identity/generator.py:18` | `accession_number.generation.value_template` |
| Präfix-Segmentierungsregeln | `planning.build_text_segments()` | Generische Regel anhand von `fields[*].generic_prefix`: wenn der Wert mit dem Präfix beginnt → `[generic(prefix), pii(rest)]`, sonst `[pii(value)]` |
| Faker-Locale | `identity/generator.py:9` | `generator.locale` |
| Faker-Aufrufrezepte + Reihenfolge | `identity/generator.py:13-18` | Reihenfolge von `fields[]` + `generation.recipe/arguments` |
| identity_id = patient_id | `runner.py:329`, `:518` | `identity_id_field` |
| Doppelte Präfixlogik in toter API | `engine/pixel_injection.py:99-138` | gelöscht, nicht migriert |
| `_TAG_META`-Keywordmenge = tag_map-Schlüssel | `runner.py:296-303` (`_build_tag_map`) | abgeleitet: alle Felder mit einer `dicom_tag`-Route |

Bleibt Code: `_FONT_FAMILY_CHOICES` / `_TEXT_BACKGROUND_CHOICES` /
`_SHOW_LABEL_BOX_CHOICES` (`runner.py:50-52`) sind Render-/CLI-Optionen, keine
Taxonomie — sie wechseln später in die Run-Konfigurationsverarbeitung unter
`config/`, liegen aber außerhalb dieses Umfangs.

## Determinismus-Constraint (Byte-Identität)

`generate_identity` versieht eine Faker-Instanz mit einem Seed und zieht in fester Reihenfolge
(`identity/generator.py:13-18`): `last_name`, `first_name`, `numerify`,
`date_of_birth`, `random_element`, `numerify`. Faker-Ausgaben hängen von der
**Aufrufreihenfolge** ab, daher muss der schema-gesteuerte Generator **in der
Listenreihenfolge von `fields[]` mit denselben Rezeptaufrufen** ziehen, um für
einen Seed identische Identitäten zu reproduzieren. Die Reihenfolge des
Beispiels entspricht absichtlich der aktuellen Reihenfolge — mit der Ausnahme,
dass heute innerhalb eines Feldes `last_name` *vor* `first_name` gezogen wird;
das Rezept `dicom_person_name` erhält diese interne Reihenfolge. Einen
Regressionstest ergänzen: Seed 42 über den schema-gesteuerten Pfad muss exakt
der heutigen Ausgabe von `generate_identity(42)` entsprechen.

`date_of_birth` darf den Ausführungstag nicht lesen. Es verwendet
`generator.reference_date` und `generator.reference_date_policy` aus dem
Schema. Das Prototype-Schema setzt `2026-07-10` als Anker des Altersfensters
fest. Das Rezept zieht den Offset des Geburtsdatums direkt über
`fake.random.randint()`, statt die Faker-eigenen
`date_of_birth()`/`date_time_ad()` aufzurufen: Diese Methoden verzweigen intern
nach `platform.system()` (`randint` unter Windows, `uniform` sonst), was bei
festem Seed nicht über Betriebssysteme hinweg reproduzierbar ist (siehe
`docs/architecture/determinism-audit.md` N14).

## Was dadurch *nicht* abgedeckt wird

- Run-/Render-Konfiguration (Schriften, Platzierung, Rotation) — eigener
  Konfigurationsbereich, späteres Paket.
- Pools mit mehreren Identitäten und dokumentübergreifende
  Identitätswiederverwendung (PLAN.md „Identity Pool“) — das Schema ist
  kompatibel (Rezepte + Seeds), die Poolsemantik ist aber künftige Arbeit.
- Neue PII-Kategorien — ausdrücklich außerhalb des Pipeline-Umfangs
  (`AGENTS.md`); das Schema erlaubt es *anderen*, sie zu definieren.

## Implementierungsstatus, 2026-07-12

Implementiert:

- `config/identifier_schema.py` validiert Generator, Felder, DICOM-Route,
  sichtbare Route, Präfix/Template und feldübergreifende Constraints.
- `configs/identifier_schemas/dicom-prototype.json` enthält die fünf Prototype-
  Felder und das deterministische Generator-Referenzdatum.
- `identity/generator.py` durchläuft Schemafelder in Dateireihenfolge und
  delegiert an `identity/recipes.py`.
- `planning.py` leitet Tag-Annotationen, sichtbaren Render-Plan und Textsegmente
  aus dem Schema ab.
- Tests decken fehlerhafte Schemas, Laden des Standardschemas, Faker-
  Referenzdatum-Determinismus, Legacy-Seed-Regressionen und einen
  E2E-Lauf mit Spielzeugschema ab.

Offen:

- `run_metadata` gibt `identifier_schema_id`, `identifier_schema_version` oder
  Schema-Pfad noch nicht aus, weil ADR-0008 keine ausgegebene additive Version
  für diese Felder besitzt.

## Implementierungsstatus

### Implementiert am 2026-07-12

- `config/identifier_schema.py` und Unit-Tests für Validierungsfehler.
- Standardschema unter `configs/identifier_schemas/`.
- Rezept-Registry und schema-gesteuertes `generate_identity(seed, schema)`.
- Planungsfunktionen lesen DICOM-Routing, sichtbares Routing und Präfixe aus
  dem Schema.
- Eingecheckte Abdeckung: E2E-Bytehash-Tests und Spielzeugschema-Smoke-Test.

### Verbleibend

- Ausgegebene Schema-Provenienz in `run_metadata`, durch ADR-0008 blockiert.

Abschlusskriterium: Der DICOM/JPG-Pfad kann mit dem Standardschema oder einem
Zwei-Felder-Spielzeugschema ohne Codeänderungen laufen. Die Ausgabe der
Provenienz bleibt außerhalb des aktuellen `0.2.0-prototype`-Records.
