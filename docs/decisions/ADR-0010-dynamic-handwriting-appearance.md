# ADR-0010: Dynamisches Handschrift-Erscheinungsbild aus kanonischen Masken

## Status

Accepted

## Kontext

DICOM- und JPG-Frames können sowohl dunkle als auch helle Bereiche enthalten.
Ein Handschrift-Asset mit einer vom Generator fest eingebrannten Tintenfarbe
ist daher nicht zuverlässig lesbar. Separate schwarze/weiße Assets würden die
Cache-Einträge vervielfachen, ohne die Handschriftform zu verändern.

## Entscheidung

Die separate Handschriftmaske ist die kanonische visuelle Quelle. Der Renderer
rekonstruiert die RGBA-Tintenschicht an der finalen Position und sampelt den
display-gemappten RGB-Frame nur unterhalb der rotierten Maske.

- Der Auto-Modus wählt bei einer mittleren Luminanz unter `128` Weiß und sonst
  Schwarz.
- Eine p10-p90-Spanne über `96`, ein Kontrast unter `64` oder weniger als acht
  gültige Samples aktivieren einen Zwei-Pixel-Halo.
- Ohne gültige Samples wird weiße Tinte mit schwarzem Halo verwendet.
- Explizite Werte `black`, `gray` oder `white` umgehen die automatische
  Farbauswahl.
- Der Halo ist rein visuell; Ground Truth verwendet weiterhin die ursprüngliche
  Tintenmaske.
- Die Generator-Cache-Identität schließt die Legacy-Präsentationsfelder
  `ink_color` und `background` aus; bei inkompatiblen alten Bundles wird die
  Renderer-Version erhöht.

## Konsequenzen

Farbänderungen erfordern keine neu erzeugten Handschrift-Assets. Render-
Metadaten speichern die gewählte Farbe, den tatsächlichen Kontrastmodus,
Luminanzstatistiken und den Entscheidungsgrund. Legacy-Manifeste bleiben
lesbar, aber ihre eingebrannte Bildfarbe oder ihr Hintergrund steuern den
kanonischen Render-Pfad nicht mehr.
