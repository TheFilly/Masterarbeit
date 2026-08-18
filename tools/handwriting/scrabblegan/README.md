# ScrabbleGAN-Handwriting-Batch-Scaffold

Dieses Verzeichnis enthält isolierte v1-Batch-Tools für Handschrift-Assets der
migrierten Injektions-Pipeline. Die Batch-Schnittstelle bleibt der
Low-Level-Generierungsvertrag; der Runtime-Asset-Provider ruft denselben
Vertrag nach der Faker-Identitätsgenerierung auf, wenn `--font-family
handwriting` ausgewählt ist.

Die Tools dienen der Manifest-Validierung, dem Hashing, Fake-Renderer-Tests,
PNG-/Masken-Postprocessing und nachgelagerten Injektionsverträgen. Der
Provider-/Cache-Pfad auf dem Host, der Befehlsvertrag des Single-Text-Wrappers,
der Options-Sidecar-Vertrag und die harten Voraussetzungstests sind
implementiert. Der Docker-/Upstream-Pfad wurde am 2026-07-15 lokal mit dem
offiziellen Source-Checkout und dem Checkpoint unter
`DicomData/HandwritingAssets/` verifiziert.

## Umfang

Version 1 unterstützt einen Batch-CLI-Workflow:

1. Ein JSONL-Eingabemanifest lesen.
2. Assets rendern oder mit dem Fake-Renderer erzeugen.
3. Bilder, Masken, Hashes, Bounding-Boxen und ein Ausgabemanifest unter
   `DicomData/HandwritingAssets/`.
4. Erzeugte Artefakte vor der Injektion validieren.

In v1 gibt es keine HTTP-API. Die Integration ergänzt in
`uv run injection-pipeline` eine lokale Cache-Suche und Generierung bei einem
Cache-Miss; die Legacy-ScrabbleGAN-Abhängigkeiten werden nicht in die
Python-3.13-Umgebung verschoben.

## Runtime-Grenze

ScrabbleGAN ist Legacy-Forschungscode und bleibt außerhalb des Python-3.13-
Projekts. Der reale Upstream-Stack benötigt eine alte
Python-/PyTorch-/CUDA-Umgebung; diese Abhängigkeiten dürfen nicht zur
Hauptumgebung hinzugefügt werden.

Lokal erzeugte Assets, Checkpoints, Source-Clones, Manifeste und Logs gehören
unter `DicomData/HandwritingAssets/` oder einen anderen ignorierten lokalen
Pfad.

## Unterstützte Prototype-Felder

- `patient_name`
- `patient_id`
- `accession_number`

Diese Namen beschreiben ausschließlich den Handschrift-Asset-Vertrag. Die
Produktions-Pipeline bleibt taxonomieagnostisch.

## Manifest-Vertrag

Eingabe-JSONL-Datensätze müssen enthalten:

- stabile `asset_id`
- `field`
- `text`
- `ink_color`: `black`, `gray` oder `white`
- `background`: `transparent` or `white`
- deterministischer `seed`

Ausgabe-Datensätze enthalten:

- Quell-`asset_id`
- Pfad zum erzeugten Bild
- Pfad zur Tintenmaske
- SHA-256 von Bild und Maske
- Checkpoint-SHA-256
- `generator_options_sha256` für den aufgelösten Options-Sidecar
- ScrabbleGAN-Repository-URL und Commit
- Rendering-Optionen
- Tinten-Bounding-Box
- Bildgröße

Pfade sind relativ zum Ausgabe-Manifest anzugeben. Absolute lokale Pfade oder
Parent-Directory-Traversal dürfen nicht in versionierte Fixtures geschrieben
werden.

## Lokales Layout

```text
DicomData/HandwritingAssets/
|-- inputs/
|   `-- batch.jsonl
|-- scrabblegan/
|   |-- checkpoints/
|   |   |-- latest_net_G.pth
|   |   `-- test_opt.txt / train_opt.txt / options.json
|   |-- source/
|   |   `-- .git_commit
|   `-- runs/
`-- logs/
```

`source/.git_commit` muss den festgelegten Upstream-Commit enthalten, wenn das
eingebundene Source-Verzeichnis kein vollständiger Git-Checkout ist. Fehlt
`.git_commit`, benötigt das Tool einen echten Git-Checkout und liest
`git rev-parse HEAD`. Den Checkpoint-Hash an jeden Render- und
Validierungsbefehl übergeben.

Der Options-Sidecar ist für echtes Rendering erforderlich. Ihn explizit mit
`--options-json`/`--handwriting-options-json` übergeben oder eine der Dateien
`options.json`, `test_opt.json`, `train_opt.json`, `test_opt.txt` oder
`train_opt.txt` neben dem Checkpoint ablegen. Das Upstream-Format von
`test_opt.txt`/
`train_opt.txt` wird akzeptiert; sein Hash wird als
`generator_options_sha256` geschrieben und fließt in die Cache-Identität ein.

## Befehle

Das Image bauen:

```powershell
docker build --platform linux/amd64 -t injection-scrabblegan tools/handwriting/scrabblegan
```

Das Image verwendet Micromamba für die historische Python-3.6-/PyTorch-1.2-
Umgebung. Dadurch bleibt der Upstream-Runtime-Vertrag erhalten, ohne den
speicherintensiven Legacy-Conda-Solver zu verwenden. Die ScrabbleGAN-Runtime
ist auf `linux/amd64` festgelegt, weil diese Legacy-Conda-Pakete für
`linux-aarch64` nicht verfügbar sind. Linux- und Windows-x86_64-Hosts führen
das Image nativ aus; Apple-Silicon- und Windows-on-ARM-Hosts verwenden Docker-
amd64-Emulation. Unter Windows mit WSL2 sollten für den initialen Build etwa
12 GB WSL-Speicher und 8 GB Swap konfiguriert werden. Der festgelegte
Legacy-Python-/PyTorch-Stack darf im Image nicht aktualisiert werden.

### macOS (zsh/bash)

Docker Desktop muss ausgeführt werden. Auf Apple Silicon verwendet Docker für
dieses Legacy-Image amd64-Emulation; `--platform linux/amd64` muss sowohl beim
Build als auch beim Run angegeben werden. Die folgenden Befehle verwenden
POSIX-Shell-Syntax:

```sh
docker build --platform linux/amd64 -t injection-scrabblegan tools/handwriting/scrabblegan
```

```sh
docker run --rm \
  --platform linux/amd64 \
  --mount "type=bind,source=$PWD,target=/workspace" \
  injection-scrabblegan \
  scrabblegan-validate \
    --manifest DicomData/HandwritingAssets/scrabblegan/runs/demo/manifest.jsonl \
    --checkpoint DicomData/HandwritingAssets/scrabblegan/checkpoints/latest_net_G.pth \
    --checkpoint-sha256 PIN_CHECKPOINT_SHA256
```

Die integrierten Host-Befehle sind unabhängig von der Shell:

```sh
uv run injection-pipeline --seed 42 --font-family handwriting
uv run injection-pipeline generate-handwriting --seed 42
```

Das getestete CPU-Image ist ungefähr 1,9 GB groß. Für Image, BuildKit-Layer/
Cache, lokale Checkpoints und erzeugte Assets sollten mindestens 5 GB frei
bleiben. Das ist ein praktischer Planungswert und keine harte Docker-Grenze;
der genaue Bedarf hängt vom lokalen Docker-Cache ab. IAM-Datensätze und
Modelltraining liegen außerhalb des Containers und benötigen zusätzlichen
Speicher.

Den Fake-Renderer für lokale Vertragsprüfungen ausführen:

```powershell
$env:PYTHONPATH = "tools/handwriting/scrabblegan"
uv run python -m scrabblegan_tool.cli render `
  --input tools/handwriting/scrabblegan/examples/batch_manifest.example.jsonl `
  --output-root DicomData/HandwritingAssets/scrabblegan/runs `
  --run-id fake-smoke `
  --source-dir DicomData/HandwritingAssets/scrabblegan/source `
  --checkpoint DicomData/HandwritingAssets/scrabblegan/checkpoints/latest_net_G.pth `
  --checkpoint-sha256 PIN_CHECKPOINT_SHA256 `
  --options-json DicomData/HandwritingAssets/scrabblegan/checkpoints/test_opt.txt `
  --fake-renderer
```

Einen Lauf validieren:

```powershell
docker run --rm `
  --platform linux/amd64 `
  -v ${PWD}:/workspace `
  injection-scrabblegan `
  scrabblegan-validate `
    --manifest DicomData/HandwritingAssets/scrabblegan/runs/demo/manifest.jsonl `
    --checkpoint DicomData/HandwritingAssets/scrabblegan/checkpoints/latest_net_G.pth `
    --checkpoint-sha256 PIN_CHECKPOINT_SHA256
```

Ein erzeugtes Manifest über den expliziten Kompatibilitätspfad verwenden:

```powershell
uv run injection-pipeline `
  --handwriting-manifest DicomData/HandwritingAssets/scrabblegan/runs/demo/manifest.jsonl `
  --handwriting-asset patient_name=patient-name-001
```

Integrierte Befehle:

```powershell
uv run injection-pipeline --seed 42 --font-family handwriting
uv run injection-pipeline generate-handwriting --seed 42
```

Der integrierte Befehl erzeugt die Faker-Identität, bevor er das Asset-Bundle
für die sichtbaren Felder `patient_name`, `patient_id` und `accession_number`
auflöst. Ein Cache-Hit verwendet kompatible Bilder und Masken erneut; ein
Cache-Miss startet das konfigurierte Docker-Image, ruft den isolierten Renderer
auf, schreibt das Bundle unter `DicomData/HandwritingAssets/` und setzt die
Injektion fort. Die genaue Cache-Identität umfasst Seed, Schema, Feld,
erzeugten Text, Checkpoint-SHA-256, Upstream-Commit, Generator-Manifest-Hash
und `options_sha256`. Bei einem Cache-Miss startet die Runtime automatisch;
fehlen Checkpoint, Options-Sidecar, Source-Metadaten, Docker-Image oder Runtime,
schlägt der Befehl ohne Font-Fallback fehl. `--handwriting-runtime-command`
bleibt als expliziter Host-Override für Tests oder eine andere isolierte Runtime
verfügbar.

Der reale Render-Pfad verwendet die IAM-englischen Checkpoint-Optionen. Der
Wrapper erstellt für Single-Word-Inferenz ein minimales temporäres Lexikon,
übergibt das passende IAM-Alphabet und die OCR-Optionen und kopiert vorhandene
Begleitdateien `latest_net_D.pth` und `latest_net_OCR.pth` neben dem Generator-
Checkpoint. Der Ausgabe-Validator akzeptiert sowohl das Low-Level-JSONL-Format
als auch das JSON-Objekt der Pipeline mit einer `assets`-Liste. Graustufen-
ScrabbleGAN-Ausgabe wird aus dem Modellbereich `[-1, 1]` normalisiert und in
eine weiche Alpha-Maske umgewandelt, wodurch antialiaste Handschriftränder
erhalten bleiben. Der Provider schreibt eine Renderer-Version in die
Cache-Identität, sodass Assets älterer Rasterisierungslogik nicht unbemerkt
wiederverwendet werden.

## Offizielle Upstream-Source lokal bereitstellen

IAM, Checkpoints, erzeugte Bilder oder andere externe Daten dürfen nicht in
versionierte Repository-Pfade kopiert werden. Die offizielle Source unter dem
ignorierten Asset-Stamm ablegen:

```powershell
git clone https://github.com/amzn/convolutional-handwriting-gan `
  DicomData/HandwritingAssets/scrabblegan/source
$commit = git -C DicomData/HandwritingAssets/scrabblegan/source rev-parse HEAD
[System.IO.File]::WriteAllText(
  "DicomData/HandwritingAssets/scrabblegan/source/.git_commit",
  $commit.Trim(),
  [System.Text.UTF8Encoding]::new($false)
)
```

Wenn das `.git`-Verzeichnis nicht erhalten werden kann, nur den Source-Baum nach
`DicomData/HandwritingAssets/scrabblegan/source` kopieren und die Datei
`.git_commit` mit dem exakten Commit-Hash beibehalten. Den trainierten
Generator-Checkpoint und den `test_opt`-/`train_opt`-Sidecar unter
`DicomData/HandwritingAssets/scrabblegan/checkpoints/` ablegen; beide Dateien
unverfolgt lassen.

## Fehlerfälle

Das Tool weist fehlende Manifeste, Source, Checkpoints, Options-Sidecars,
Source-Commit-Metadaten, unbekannte Felder, ungültige Farben oder Hintergründe,
leeren Text, doppelte `asset_id`s, Checkpoint-Hash-Abweichungen, leere Masken,
abweichende Bild-/Maskengrößen, ungültige Hashes, absolute Pfade,
Parent-Directory-Traversal, Text außerhalb des Checkpoint-Alphabets und weiße
Tinte auf weißem Hintergrund zurück.

Individuelle Render-Fehler werden in `failures.jsonl` geschrieben; erfolgreiche
Assets in `manifest.jsonl`.
