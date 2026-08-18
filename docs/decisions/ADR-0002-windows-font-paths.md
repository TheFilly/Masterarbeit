---
id: ADR-0002
status: accepted
based_on:
  - docs/architecture/determinism-audit.md
---

# ADR-0002: Feste Windows-Font-Pfade für Prototype-Text-Rendering

Nachgetragen am 2026-07-06. Hält eine bereits im Code umgesetzte Entscheidung
fest.

## Kontext

Die sichtbare Pixel-Injektion rendert synthetische PII mit PIL und benötigt
konkrete TrueType-Fonts. Der Prototype zielt auf eine einzelne Windows-
Entwicklungsmaschine; die gerenderte Glyphengeometrie und damit Ground-Truth-
Boxkoordinaten und eingefrorene byte-identische Validierungsartefakte hängen
von den exakten Font-Dateien ab.

## Entscheidung

Font-Familien bilden eine abgeschlossene Menge, die in
`engine/pixel_injection.py:19-24` auf absolute Windows-Pfade abgebildet wird
(`_FONT_PATHS`: arial, calibri, tahoma, consolas unter `C:/Windows/Fonts/`).
Eine fehlende Font löst zur Laufzeit einen Fehler aus (`load_default_font`,
`engine/pixel_injection.py:77`). Die CLI stellt dieselbe abgeschlossene Menge
bereit (`runner.py:50`, `cli.py:280-289`).

## Betrachtete Alternativen

- **Font-Erkennung über matplotlib/fontconfig**: für den Prototype abgelehnt –
  die Erkennungsreihenfolge hängt von der Umgebung ab und würde die
  Geometrie-Reproduzierbarkeit brechen.
- **Fonts im Repository bündeln**: für Portabilität am saubersten, aber mit
  Lizenzfolgen (Windows-Systemfonts dürfen nicht weiterverteilt werden);
  zurückgestellt.

## Konsequenzen

- Deterministisches Rendering auf der primären Maschine; eingefrorene
  Validierungsartefakte bleiben vergleichbar.
- Die Pipeline ist nicht portabel: Jede Nicht-Windows-Umgebung (einschließlich
  CI) schlägt beim Laden der Font fehl. Font-*Dateiversionen* sind eine nicht
  aufgezeichnete Reproduzierbarkeitseingabe (siehe
  `docs/architecture/determinism-audit.md`, N7).
- Ersetzender Pfad: Font-Konfiguration externalisieren (WP-C-Identifier-/Run-
  Konfiguration) und Font-Datei-Hashes im Run-Record aufzeichnen (WP-G). Für
  CI eine frei lizenzierte Font (z. B. DejaVu) bündeln oder festlegen.

## Review-Hinweise

Durch WP-H nachgetragen. Vor CI- oder Multi-Machine-Arbeiten erneut prüfen.
