---
id: ADR-0007
status: accepted
based_on:
  - docs/decisions/ADR-0003-synthetic-prefix-conventions.md
  - docs/architecture/identifier-schema-spec.md
---

# ADR-0007: Die PII-Taxonomie wird in ein externes Identifier-Schema unter `configs/` verschoben

## Kontext

Vor WP-C waren Identitätsfelder, Generierungsrezepturen, DICOM-Routen, Routen
für sichtbare Pixel und synthetische Präfixe als Literale über Runner- und
Identitätscode verteilt. `AGENTS.md` verbietet das Hardcodieren von
PII-Kategorien in der Produktionslogik und erklärt die „Definition von
PII-Kategorien“ für die Pipeline als außerhalb des Umfangs.

## Entscheidung

Ein versioniertes JSON-Identifier-Schema einführen (Format spezifiziert in
`docs/architecture/identifier-schema-spec.md`) unter
`configs/identifier_schemas/dicom-prototype.json`, das von
`config/identifier_schema.py` in pydantic-Modelle geladen wird. Jeder
Feldeintrag deklariert Name, Generierungsrezept (Faker-Provider plus Argumente
und Wertvorlage), synthetisches Präfix (falls vorhanden) und Routing
(DICOM-Tag-Adresse/VR/Keyword, sichtbare Darstellung mit Zeilenindex oder nur
Tag). `identity/` und der Injection-Planner verwenden das Schema; die fünf
aktuellen Felder bilden die erste konkrete Instanz des Schemas und reproduzieren
das bisherige Verhalten exakt.

JSON (nicht YAML/TOML) wird verwendet, um der Konfigurationsentscheidung des
PDF-Plans zu entsprechen und eine neue Abhängigkeit zu vermeiden.

## Betrachtete Alternativen

- **Python-Konfigurationsmodul** (Felder als Konstanten in `config/`):
  zentralisiert, externalisiert aber nicht – ein Wechsel der Taxonomie
  erfordert weiterhin Codeänderungen, und die These „taxonomieagnostisch“
  bleibt unbelegt.
- **YAML-Schema**: einfacher manuell zu bearbeiten, fügt aber eine
  Abhängigkeit hinzu; zurückgestellt, da die Loader-Grenze einen späteren
  Formatwechsel kostengünstig macht.
- **Datenbank/Registry von Identifier-Typen**: für dieses Projekt zu groß
  dimensioniert.

## Konsequenzen

- Das zentrale Prinzip aus `AGENTS.md` wird nachweisbar: Eine andere Taxonomie
  ist eine andere JSON-Datei und keine Codeänderung (Evidenz für Thesis FF1).
- Ausgabereihenfolge der Identitätsgenerierung und Faker-Aufrufreihenfolge
  müssen bei instanzbasiertem Seeding exakt erhalten bleiben, sonst ändern sich
  Identitäten für einen Seed (Byte-Identitätsrisiko; die Spezifikation fixiert
  die Aufrufreihenfolge).
- Die Validierung verschiebt sich auf die Ladezeit: Ein fehlerhaftes Schema
  schlägt fehl, bevor eine Datei angefasst wird.

## Implementierungsstatus

Am 2026-07-12 für die Prototype-Taxonomie implementiert:

- `configs/identifier_schemas/dicom-prototype.json` enthält die fünf aktuellen
  Felder, Generierungsrezepturen, DICOM-Routen, sichtbaren Routen, Präfixe und
  `generator.reference_date = "2026-07-10"`.
- `config/identifier_schema.py` validiert das Schema mit pydantic-Modellen.
- `identity/generator.py` und `identity/recipes.py` erzeugen `Identity` aus
  dem Schema und erhalten die Faker-Aufrufreihenfolge.
- `planning.py` leitet Tag-Pläne, sichtbare Render-Pläne und Textsegmente aus
  dem Schema ab. Die E2E-Suite enthält einen Schema-Smoke-Test mit anderen
  Feldern.

Noch offen: Die Provenienz des ausgegebenen Identifier-Schemas in
`run_metadata` wartet auf ADR-0008.

## Review-Hinweise

Mit der WP-C-Implementierung am 2026-07-12 angenommen. Die Semantik von
Identitätspools bleibt zukünftige Arbeit.
