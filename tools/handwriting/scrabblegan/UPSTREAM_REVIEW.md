# Upstream-Review: ScrabbleGAN-Batch-Tooling gegenüber amzn/convolutional-handwriting-gan

Datum: 2026-06-11. Das lokale v1-Batch-Tooling wurde mit dem offiziellen
Amazon repository (`https://github.com/amzn/convolutional-handwriting-gan`,
README und `environmentPytorch12.yml` auf `master`) verglichen.

Aktualisierung des Implementierungsstatus: Die folgenden Blocker wurden durch
den Einzeltext-Wrapper des Repositorys, das Micromamba-CPU-Image, den
Checkpoint-Options-Adapter, die Verarbeitung von Begleit-Checkpoints und
Änderungen an der Manifestkompatibilität behoben. Der echte Docker-/Upstream-
Pfad wurde am 2026-07-15 mit dem lokalen IAM-Checkpoint verifiziert. Diese
Datei bleibt der historische Review-Bericht; die aktuellen Betriebsanweisungen
stehen in `tools/handwriting/scrabblegan/README.md`.

## Urteil

Das ursprüngliche Review-Urteil war, dass der lokale Code nur ein Batch-
Grundgerüst darstellte. Dieses Urteil galt vor der oben beschriebenen
Implementierungsarbeit und bleibt unten als historischer Kontext erhalten.

## Befunde

### 1. Die angenommene Inferenzschnittstelle existiert im Upstream nicht (Blocker)

`render.py` defaults to calling
`generate.py --text {text} --seed {seed} --checkpoint {checkpoint} --output {output}`
im eingebundenen Source-Verzeichnis auf. Das offizielle Repository besitzt
**kein `generate.py`** und kein Skript, das eine Textzeichenfolge in eine PNG
rendert. Die Upstream-Generierung erfolgt über
`generate_wordsLMDB.py`, wobei:

- sampelt Wörter aus einem **Lexikon** (kein `--text`),
- schreibt **LMDB-Datenbanken mit TIFF-Bildern** (kein `--output <png>`),
- besitzt keinen **`--seed`**-Parameter,
- lädt das Modell über die Pix2pix-artige Mechanik
  `TestOptions`/`create_model()` (`--name <experiment>`), nicht über ein
  `--checkpoint <file>`-Flag.

**Erforderliche Änderung:** Einen kleinen eigenen Inferenz-Wrapper (z. B.
`generate_single.py`) schreiben, der in diesem Repository liegt und in das
Image kopiert oder neben dem Source eingebunden wird. Er muss das Options-
Objekt aufbauen, `netG`-Gewichte laden, den angeforderten Text mit dem
Datenalphabet kodieren, `torch.manual_seed`/`numpy.random.seed`/`random.seed`
aus dem Manifest-Seed setzen, den Generator ausführen und eine PNG nach
`--output` schreiben. Anschließend diesen Wrapper statt des fiktiven
`generate.py` als dokumentierten `--generator-command` (oder eingebauten
Standard) verwenden.

### 2. Das Docker-Image kann ScrabbleGAN nicht ausführen (Blocker)

- **PyTorch wird nie installiert.** Die einzige installierte Python-
  Abhängigkeit ist `Pillow<8`; das ARG/ENV `PYTORCH_VERSION` ist toter Code.
  Upstream benötigt PyTorch 1.2.0, torchvision 0.2.1, numpy, lmdb, opencv usw.
  (siehe `environmentPytorch12.yml`).
- **Falsche CUDA-Basis.** Das Basis-Image ist `nvidia/cuda:9.0-...`. Der
  Upstream-README-Text nennt „CUDA 9.0“, aber die festgelegte Conda-Umgebung
  verwendet `cudatoolkit 10.0.130`, und PyTorch-1.2.0-Binaries existieren nur
  für CUDA 9.2/10.0. Eine CUDA-10.0- plus cuDNN-7-Basis verwenden.
- **`apt-get install python3.6` schlägt unter Ubuntu 16.04 fehl.** Xenial
  liefert Python 3.5; 3.6 erfordert das deadsnakes-PPA oder (besser) Miniconda.
  Die sauberste Korrektur ist, Miniconda zu installieren und die Umgebung aus
  Upstreams `environmentPytorch12.yml` zu erzeugen (Python 3.6.8, PyTorch 1.2.0,
  cudatoolkit 10.0).
- **Risiko der Tag-Verfügbarkeit.** Alte `nvidia/cuda`-Tags für CUDA 9/10 auf
  ubuntu16.04 wurden mit der Zeit aus Docker Hub entfernt; den gewählten Tag
  vor der Verwendung prüfen (oder aus `nvcr.io` beziehen).

### 3. Der Checkpoint-Vertrag passt nicht zum Upstream (Blocker)

Das Tooling erwartet einen einzelnen eingebundenen `model.pth`. Upstream speichert Gewichte als
`<checkpoints_dir>/<experiment_name>/<epoch>_net_G.pth` und lädt sie über
`model.setup(opt)`. Außerdem werden **keine vortrainierten Gewichte
veröffentlicht** — das Modell muss lokal auf IAM/RIMES/CVL trainiert werden
(Datensätze müssen manuell beschafft werden). Entscheiden und dokumentieren:

- ob der eigene Wrapper direkt ein rohes `net_G.pth`-State-Dict lädt (dann ist
  eine einzelne eingebundene Datei ausreichend; SHA-256-Festlegung beibehalten),
  und
- dass das Training eines Checkpoints eine Voraussetzung ist (das README
  erweckt derzeit den Eindruck, ein Checkpoint existiere einfach).

### 4. Der Hintergrundmodus `transparent` funktioniert nur mit dem Fake-Renderer (Fehler)

Die echte ScrabbleGAN-Ausgabe ist ein Graustufenbild mit weißlichem Hintergrund
und **ohne Alphakanal**. `masks._build_mask` verwendet bei
`background == "transparent"`; nach `convert("RGBA")` hat jedes Pixel den
Alpha-Wert 255, daher wird die Maske zum vollständigen Bild und die normalisierte
Ausgabe zu einem soliden Tintenrechteck.

**Erforderliche Änderung:** Die Tintenmaske immer aus dem Abstand-zu-Weiß-
Schwellenwert ableiten (oder Alpha nur verwenden, wenn das Rohbild tatsächlich
einen nichttrivialen Alphakanal besitzt) und `background` ausschließlich für
das Compositing der normalisierten Ausgabe verwenden.

### 5. Textbeschränkungen werden nicht gegen das Modellalphabet validiert (Lücke)

ScrabbleGAN generiert mit einem festen Alphabet pro Datensatz (z. B. entfernt
`IAMcharH32rmPunct` Satzzeichen) bei 32 px Höhe und etwa 16 px Breite pro
Zeichen. Folgen für die v1-Felder:

- Werte von `patient_id` / `accession_number` mit Ziffern, Bindestrichen oder
  anderen Symbolen können außerhalb des trainierten Alphabets liegen und
  unbrauchbare Glyphen erzeugen.
- `patient_name` mit Leerzeichen/Umlauten: Leerzeichen sind nicht Teil der
  Generierung auf Wortebene; mehrteilige Namen benötigen wahrscheinlich
  Generierung pro Wort und anschließendes Compositing.

**Erforderliche Änderung:** `text` des Manifests in `manifest.py` gegen das
Checkpoint-Alphabet validieren (ablehnen oder transliterieren) und eine
Strategie für mehrteilige Namen entscheiden.

### 6. Kleinigkeit

- `ink_color: "white"` mit `background: "white"` besteht zwar die Validierung,
  erzeugt aber ein unsichtbares Asset (die Maske enthält weiterhin die Form;
  die Kombination markieren oder ablehnen).
- Die Python-Pixel-Schleife in `masks._build_mask` ist für große Batches
  langsam; eine numpy-/`Image.point`-Lösung wäre in der Container-Umgebung
  leicht einzuführen (numpy ist nach Installation der Upstream-Umgebung
  verfügbar).

## Was bereits solide ist

Die Isolation des Containers vom Python-3.13-Projekt, der JSONL-Manifestvertrag,
die SHA-256-Festlegung von Checkpoint/Bild/Maske, die Durchsetzung relativer
Pfade, Fehlerprotokollierung, der Fake-Renderer für die CI und die
Manifestvalidierung nach dem Run entsprechen alle dem vorgesehenen Design und
können unverändert bleiben.
