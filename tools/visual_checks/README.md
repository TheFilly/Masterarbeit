# Visuelle Prüfungen

Dieses Verzeichnis enthält manuell gestartete Skripte zur visuellen Prüfung
des Pipeline-Verhaltens. Die Skripte liegen absichtlich außerhalb der
automatisierten pytest-Suite und können Docker starten, Ausgabe-Artefakte
schreiben oder lokale Modellgewichte verwenden.

## Vollständige Funktionssuite

Aus dem Repository-Stamm ausführen:

```powershell
uv run python tools/visual_checks/pipeline_functionality.py
```

Das Skript erstellt ein neues Verzeichnis mit Zeitstempel unter
`output/visual-checks/`, sodass sich wiederholte manuelle Läufe nicht mit
früheren Run-Bundles überschneiden. Es verwendet `pathlib` und Argumentlisten
statt Shell-spezifischer Pfadtrenner oder Quoting, daher funktioniert derselbe
Befehl unter Windows und macOS.

Die Suite deckt ab:

- normale DICOM- und JPG-CLI-Injektion;
- alle standardmäßigen Font-Familien, Rotationen, Platzierungsmodi,
  Schriftgrößen, Hintergrundmodi und Optionen für die Label-Box-Preview;
- Handschrift-CLI-Injektion mit den Tintenfarben `auto`, `black`, `gray` und
  `white` sowie beiden Kontrastmodi;
- den eigenständigen Befehl `generate-handwriting`;
- sowohl `inject-pdf` als auch dessen Alias `compose-pdf`;
- die öffentliche Funktion `inject_function` für native DICOM-Felder,
  benutzerdefinierte JPG-Kategorien sowie DICOM- und JPG-Handschrift;
- die öffentliche Funktion `make_pdf` mit direktem PDF-Text, mehreren Bildern,
  Annotationsübertragung und einem größeren Layout-/Ablauftest;
- fokussierte pytest-Prüfungen für `test_api.py` und `test_make_pdf_api.py`,
  die nur beim Start dieser manuellen Suite ausgeführt werden.

Handschrift-Szenarien benötigen das Docker-Image `injection-scrabblegan` sowie
die lokalen Checkpoint-/Source-Voraussetzungen. Nur die Prüfungen ohne
Handschrift ausführen:

```powershell
uv run python tools/visual_checks/pipeline_functionality.py --skip-handwriting
```

Weitere nützliche Teilmengen:

```powershell
uv run python tools/visual_checks/pipeline_functionality.py --skip-pdf
uv run python tools/visual_checks/pipeline_functionality.py --skip-api
uv run python tools/visual_checks/pipeline_functionality.py --skip-unit-tests
```

Die direkte `make_pdf`-API akzeptiert derzeit bereits gerenderte Bild-Assets
und direkten PDF-nativen Text. Eine direkte PDF-Texteingabe mit
`handwritten=True` bleibt absichtlich nicht unterstützt und ist nicht als
erfolgreiche Visual Check enthalten.

## Einzelne Handschrift-Alphabetprüfung

Für die kleinere Prüfung der Zeichenqualität:

```powershell
uv run python tools/visual_checks/handwriting_alphabet.py
```

Erzeugte Dateien gehören unter `output/` und werden nicht versioniert.
