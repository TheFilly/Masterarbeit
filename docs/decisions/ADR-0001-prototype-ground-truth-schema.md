---
id: ADR-0001
status: accepted
based_on:
  - docs/dicom-injection.md
---

# ADR-0001: Prototype-Ground-Truth-Schema `0.2.0-prototype` als manuell erzeugter JSON-Datensatz

Nachgetragen am 2026-07-06. Hält eine bereits im Code umgesetzte Entscheidung
fest.

## Kontext

Die migrierte DICOM/JPG-Pipeline benötigte ein Ground-Truth-Artefakt, bevor das
formatagnostische Dokumentmodell (`PLAN.md`, Phase 2) existierte. `PLAN.md`
plante ein JSONL-Ground-Truth-Format; der Prototype wurde vor dieser
Designarbeit ausgeliefert.

## Entscheidung

Der Prototype etablierte ein JSON-Objekt pro Run mit
`schema_version = "0.2.0-prototype"`. Bei der Übernahme wurde es manuell
zusammengesetzt und besaß kein validierendes Modell;
`docs/dicom-injection.md` dokumentiert die Felder.

## Betrachtete Alternativen

- **JSONL-Datensätze pro Annotation** (Richtung von `PLAN.md`): zurückgestellt;
  ein einzelnes JSON-Objekt pro Run war einfacher, solange sich die
  Annotationsformen noch änderten.
- **pydantic-Modelle von Anfang an**: zurückgestellt, damit die Prototype-
  Migration byte-identisch mit der Ausgabe vor dem Package bleibt.

## Konsequenzen

- Der ursprüngliche Builder ließ sich schnell iterieren und bewahrte die
  Byte-Identität der Migration.
- Vor ADR-0005 konnte ein Tippfehler in einem Schlüssel das Schema unbemerkt
  ändern; Verbrauchern stand außer dem dokumentierten Beispiel kein
  validierter Vertrag zur Verfügung.
- Der PDF-Plan führt einen zweiten, anders versionierten Sidecar ein
  (`0.3.0-pdf-prototype`), was ohne vereinheitlichende Strategie unweigerlich
  zu Abweichungen führt.
- Ersetzender Pfad: WP-B (`docs/architecture/domain-model-spec.md`) entwirft
  den typisierten Ersatz; ADR-0008 definiert den Versionszusammenhang. Dieses
  ADR bleibt als Baseline des ausgegebenen Prototype-Formats `accepted`.

## Implementierungsstatus

Der manuell erstellte Builder wurde am 2026-07-12 durch
`ground_truth.build_record()` und das validierte `RunRecord` aus ADR-0005
ersetzt. Die Pipeline parst und erzeugt weiterhin den Artefaktvertrag
`0.2.0-prototype`; daher bleibt dieses ADR die historische Baseline für diese
veröffentlichte Version.

## Review-Hinweise

Durch WP-H nachgetragen; die Entscheidung war in der Prototype-Migration
(Commit `0be8818` und frühere) implizit enthalten.
