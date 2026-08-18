---
id: ADR-0008
status: accepted
based_on:
  - docs/decisions/ADR-0001-prototype-ground-truth-schema.md
  - docs/pdf-template-injection-plan.md
  - docs/architecture/domain-model-spec.md
---

# ADR-0008: Eine versionierte Schema-Linie für alle Ground-Truth-Artefakte

## Kontext

`0.2.0-prototype` ist die aktuelle Version des DICOM/JPG-Run-Records. Die
PDF-Modalität führt für ihren eigenen Annotation-Sidecar
`0.3.0-pdf-prototype` ein; sie akzeptiert ein Eingabe-PDF sowie ein injiziertes
DICOM und eine validierte JSON-Annotation. Zwei unabhängig fortgeschriebene
Versionszeichenfolgen ohne gemeinsame Regeln würden zwangsläufig auseinander-
laufen, daher bleiben beide Records in einer gemeinsamen Versionslinie.

## Entscheidung

- **Eine Versionslinie, zwei Dokumentarten.** `RunRecord` (Ground Truth pro Run)
  und `PdfAnnotationRecord` (PDF-Sidecar) sind durch `record_type` unterschiedene
  Dokumentarten, teilen sich aber eine gemeinsame Nummerierung von
  `schema_version` und ein gemeinsames Changelog
  (`docs/architecture/domain-model-spec.md`, „Versioning“).
- **Semver mit Pre-Release-Tags.** `MAJOR.MINOR.PATCH[-tag]`: MAJOR = nicht
  rückwärtskompatible Leseänderungen, MINOR = zusätzliche Felder, PATCH =
  Korrekturen an Dokumentation oder Constraints. Die Tags `-prototype` /
  `-pdf-prototype` kennzeichnen Versionen vor der Stabilität; die typisierten
  Modelle beginnen bei `0.4.0` (erste validierte Version), während bis zu einem
  künftigen ADR weiterhin `0.2.0-prototype` *ausgegeben* wird.
- **Rückwärtskompatibilität durch den Parser, nicht durch Einfrieren.** Die
  Modelle müssen Dateien mit `0.2.0-prototype` und `0.3.0-pdf-prototype`
  einlesen können (permissive Lesemodelle oder explizite Migrationsfunktionen);
  Golden Files unter `tests/fixtures/schemas/` halten jede veröffentlichte
  Version fest.

## Betrachtete Alternativen

- **Unabhängige Versionen pro Artefaktart**: Das würde der PDF-Plan nahelegen;
  die Versionen driften sofort auseinander, und gemeinsame Submodelle (Punkte,
  Boxen) erhielten zwei Versionsgeschichten.
- **Keine Versionen bis zur Stabilität**: Beseitigt die Abweichung, indem es
  Informationen beseitigt. Bestehende Artefakte enthalten bereits
  Versionszeichenfolgen, daher kann das Feld nicht entfallen.
- **JSON-Schema-Dateien als Quelle der Wahrheit**: Eine Verdopplung der
  pydantic-Modelle; sie können später bei Bedarf für externe Konsumenten aus
  den Modellen *generiert* werden.

## Konsequenzen

- Eine Schemaänderung bedeutet: Version an einer Stelle erhöhen, eine Golden
  File hinzufügen und einen Changelog-Eintrag ergänzen. Alte Artefakte bleiben
  einlesbar.
- Der PDF-Sidecar verwendet gemeinsame Geometriemodelle aus `models/`, während
  Seiten-, Platzierungs- und PDF-Dateimodelle unter
  `injection_pipeline/pdf/` verbleiben.

## Implementierungsstatus

Am 2026-07-14 angenommen und teilweise implementiert:

- `RunRecord` validiert und erzeugt weiterhin das bestehende DICOM/JPG-Record
  `0.2.0-prototype`.
- `load_run_record()` akzeptiert nur `0.2.0-prototype`; Tests halten das
  Round-Trip-Verhalten fest.
- Das gemeinsame Schema-Changelog wird unter
  `docs/architecture/schema-changelog.md` gepflegt.

Noch offen:

- Das ausgegebene DICOM/JPG-Record hat noch keinen versionssicheren Platz für
  die Provenienz des Identifier-Schemas oder den `reproducibility`-Block aus
  ADR-0009.
- Die Sidecar-Modelle `0.3.0-pdf-prototype` sowie PDF-Loader und -Writer sind
  gemäß dem freigegebenen PDF-Plan implementiert; eine breitere Abdeckung mit
  operativen Fixtures ist noch in Arbeit.

## Review-Hinweise

Vom Projektverantwortlichen am 2026-07-14 angenommen. Künftige
Schemaänderungen benötigen einen Changelog-Eintrag; nicht rückwärtskompatible
Änderungen benötigen ein ersetzendes ADR.
