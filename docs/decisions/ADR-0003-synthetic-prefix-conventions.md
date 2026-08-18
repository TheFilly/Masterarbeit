---
id: ADR-0003
status: accepted
based_on:
  - docs/architecture/identifier-schema-spec.md
---

# ADR-0003: `SYNTH-`-/`ACC-`-Präfixe markieren synthetische Identifier und trennen PII von allgemeinem Text

Nachgetragen am 2026-07-06. Hält eine bereits im Code umgesetzte Entscheidung
fest.

## Kontext

Injizierte Identifier müssen erkennbar synthetisch sein (Sicherheit: Niemand
soll eine injizierte Patient-ID mit einer echten verwechseln). Nachgelagerte
Auswertung muss die PII-Nutzlast innerhalb einer gerenderten Zeichenkette von
allgemeinem Gerüst unterscheiden können, damit Detektormetriken das Auffinden
des konstanten Präfixes nicht belohnen.

## Entscheidung

- Das Standard-Identifier-Schema erzeugt `patient_id = "SYNTH-" + 6 digits`
  und `accession_number = "ACC-" + 7 digits`.
- `planning.build_text_segments()` teilt gerenderten Text anhand des
  konfigurierten Präfixes jedes Felds in allgemeine und PII-Segmente.
- Der Renderer führt getrennte Masken pro Segmenttyp und gibt über die in
  `engine/injector.py` erstellten Annotationsmodelle `corners` für den PII-Teil
  und `label_corners` für den Präfix-Teil aus.

## Betrachtete Alternativen

- **Kein Präfix**: abgelehnt – synthetische Werte wären nicht von plausiblen
  echten Werten unterscheidbar.
- **Markierung nur als Wasserzeichen/Metadatum**: abgelehnt – die Markierung
  muss in den sichtbaren Pixeln erhalten bleiben, in denen die injizierte PII
  liegt.

## Konsequenzen

- Ground Truth kann PII-Boxen von Präfix-Boxen (`label_corners`) trennen; die
  annotierte Preview visualisiert diese über `--show-label-boxes`.
- Die Präfixregeln lagen ursprünglich als duplizierte Stringliterale vor.
  ADR-0007 verschob sie in das externe Identifier-Schema, und
  `planning.build_text_segments()` verwendet nun diese Konfiguration.
- Die Konvention bleibt stabil, während die konkrete Präfix-Taxonomie in Daten
  statt in der Pipeline-Logik liegt.

## Review-Hinweise

Durch WP-H nachgetragen. Die Konvention beibehalten, die Daten aber verlagern.
