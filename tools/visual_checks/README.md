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

## Echte DICOM-Daten mit `make_pdf`

Der folgende manuelle Check verwendet ausschliesslich vorhandene lokale
Single-Frame-DICOMs aus `DicomData/Dicom-Files` sowie zwei JPG/JPEG-Dateien pro
Fall aus `DicomData/images`. Alle drei Bildquellen werden vor `make_pdf` ueber
die oeffentliche `inject_function` injiziert. Die roten Boxen in der
annotierten PDF stammen aus den jeweiligen Ground-Truth-Annotationen; der
zweite Fall verwendet eine DICOM-Textrotation von 90 Grad:

```bash
uv run python tools/visual_checks/dicom_make_pdf_real_data.py
```

Mit `--cases 1` bis `--cases 3` kann die Anzahl der Faelle begrenzt werden.
Die Artefakte werden standardmäßig unter einem Zeitstempel-Unterordner von
`output/visual-checks/dicom-make-pdf-real-data/` geschrieben. Mit
`--output-root` kann das Ziel weiterhin explizit festgelegt werden.
Der Basis-Seed ist standardmäßig `9100`; pro Fall wird `seed + case_number`
verwendet. Die beiden JPG-Dateien werden pro Fall ab einem fallabhängigen
Index ausgewaehlt und bei zu wenigen Dateien zyklisch wiederverwendet. Die
JPG-Injektionen verwenden jeweils Rotation `0` und eigene Run-IDs.
Für vollständig reproduzierbare Run-IDs zusätzlich einen festen ISO-8601-
Zeitstempel setzen, zum Beispiel:

```bash
uv run python tools/visual_checks/dicom_make_pdf_real_data.py \
  --cases 3 --seed 9100 --run-timestamp 2026-09-16T12:00:00
```

## Einzelne Handschrift-Alphabetprüfung

Für die kleinere Prüfung der Zeichenqualität:

```powershell
uv run python tools/visual_checks/handwriting_alphabet.py
```

Erzeugte Dateien gehören unter `output/` und werden nicht versioniert.
