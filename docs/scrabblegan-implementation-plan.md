# ScrabbleGAN-Handschriftgenerierung — Implementierungsplan

Status: **teilweise umgesetzt – Provider-/Cache-Integration auf dem Host,
automatische Docker-Runtime-Verdrahtung, Verifizierung des echten Checkpoints
und Soft-Alpha-Rasterverarbeitung abgeschlossen; ADR- und vollständige
Test-Gate-Nacharbeiten bleiben offen**.
Der Fake-Renderer, Manifest-, Hashing- und Validierungs-Scaffold, der integrierte
Pfad `--font-family handwriting` und der eigenständige Pfad
`generate-handwriting --seed` existieren. Der reale ScrabbleGAN-Lauf wurde am
2026-07-15 mit offiziellem Source-Checkout, `.git_commit`-Metadaten und lokalem
Checkpoint-/Options-Sidecar verifiziert.

Erstellt am 2026-07-10. Basiert auf den Ergebnissen aus
`tools/handwriting/scrabblegan/UPSTREAM_REVIEW.md` (Upstream-Vergleich
mit `https://github.com/amzn/convolutional-handwriting-gan`). Der bestehende
Batch-Scaffold (Manifest-Vertrag, Hashing, Validierung, Fake-Renderer,
Container-Isolation) bleibt erhalten. Dieser Plan schließt die Lücke zwischen
Scaffold und einer funktionierenden Realmodell-Pipeline und dokumentiert und
testet anschließend das Ergebnis.

Ziel: Echte ScrabbleGAN-Handschrift-Assets (Bild + Tintenmaske + Manifest) in
der isolierten Legacy-Umgebung erzeugen und in
`uv run injection-pipeline` reproduzierbar von Anfang bis Ende nutzen. Im
Handschriftmodus erzeugt die Pipeline zuerst die Faker-Identität,
sucht den resultierenden Seed im lokalen Handschrift-Asset-Speicher, erzeugt
fehlende Assets, hängt sie an den Render-Plan an und persistiert sie für spätere
Läufe. Ein separater Konsolenbefehl akzeptiert einen Seed und erzeugt dasselbe
Asset-Bundle vorab, ohne ein Dokument zu injizieren.

## Umfang

- Enthalten:
  - Eine ausführbare Legacy-Container-Umgebung mit Upstream-Umgebung (Python
    3.6.8, PyTorch 1.2.0) und installiertem Batch-Tool.
  - Ein eigener Single-Text-Inference-Wrapper um den Upstream-Generator
    (Upstream besitzt kein solches Skript – Review-Ergebnis 1).
  - Ein trainierter oder anderweitig beschaffter, per SHA-256 festgelegter
    Generator-Checkpoint.
  - Korrekturen am Batch-Tool: Maskenfehler bei transparentem Hintergrund
    (Ergebnis 4), Alphabetvalidierung (Ergebnis 5), unsichtbare Kombination
    aus Weiß auf Weiß (Ergebnis 6).
  - Ein verifizierter End-to-End-Lauf: Batch-Manifest → Container-Rendering →
    validiertes Ausgabe-Manifest → DICOM-Injektion mit visueller Prüfung.
  - Ein integrierter Handschrift-Render-Modus im DICOM/JPG-Injektionsfluss:
    Faker-Identitätsgenerierung → Asset-Suche → Erzeugung fehlender Assets →
    Handschrift-Overlay-Injektion → persistente Manifeste/Artefakte unter
    `DicomData/HandwritingAssets/`.
  - Ein eigenständiger seed-basierter Handschriftgenerierungsbefehl mit
    demselben Cache- und Generatorvertrag wie der integrierte Modus.
  - Interaktive CLI-Reihenfolge, in der der Seed vor der gemeinsamen
    Font-/Renderer-Auswahl und den übrigen Render-Parametern festgelegt wird.
  - Tests (Unit-Tests auf dem Host, Container-Smoke-Test,
    Determinismusprüfung, Integrationstest) und Dokumentationsaktualisierungen
    einschließlich Abschluss dieses Plans und der Review-Datei.
- Nicht enthalten:
  - HTTP-API um den Batch-Kern (laut v1-README ausdrücklich zurückgestellt).
  - Neue Identitätsfelder über `patient_name`, `patient_id` und
    `accession_number`.
  - Style-Conditioning auf Modellebene über gewählten Renderer und Seed hinaus;
    ScrabbleGAN-Noise-Vector-Stile bleiben implizit über den Seed, sofern eine
    spätere Entscheidung keinen expliziten Style-Parameter ergänzt.
  - Versionieren von Datensätzen, Checkpoints oder erzeugten Assets (sie bleiben
    unter `DicomData/` und sind durch Git ignoriert).

## Entscheidungen

### Bestätigter Integrationsvertrag

- Der bestehende manifestgesteuerte Pfad bleibt ein unterstützter Low-Level-
  Vertrag für explizite Asset-Injektion und Tests.
- Der neue integrierte Pfad verwendet eine gemeinsame
  `--font-family`-/interaktive Auswahl. Sie umfasst die normalen Font-Optionen
  (`arial`, `calibri`, `tahoma`, `consolas`) sowie `handwriting`. Die Auswahl
  `handwriting` ruft nach der Faker-Identitätsgenerierung einen Asset-Provider
  auf; normale Auswahlen behalten den bestehenden Pillow-Renderpfad.
- Der Asset-Provider muss von Injektions-CLI und eigenständigem Seed-Befehl
  gemeinsam verwendet werden, damit ein vorab erzeugter Seed bei der Injektion
  wiederverwendet wird.
- Handschrift wird nur für die derzeit sichtbaren Identitätsfelder erzeugt:
  `patient_name`, `patient_id` und `accession_number`.
- Der Cache ist ein Seed-Bundle, aber ein Asset ist nur wiederverwendbar, wenn
  seine Cache-Identität mit Seed, Identifier-Schema-ID/-Version, Identitätsfeld,
  erzeugtem Text, ScrabbleGAN-Checkpoint-SHA-256, Upstream-Commit,
  Generator-Manifest-Hash und Options-Sidecar-SHA-256 (`options_sha256` /
  `generator_options_sha256`) übereinstimmt. Eine geänderte Identität oder ein
  geänderter Generatorvertrag erzeugt ein neues kompatibles Asset, statt alte
  Ausgabe stillschweigend wiederzuverwenden.
- Asset-Suche und -Schreiben sind lokale Dateisystemoperationen unter
  `DicomData/HandwritingAssets/`; erzeugte Bilder, Masken, Manifeste,
  Checkpoints und Quellcode von Drittanbietern bleiben nicht versioniert.
  - Integrierter und eigenständiger Modus starten die isolierte ScrabbleGAN-
    Runtime bei einem Cache-Miss automatisch. Wenn Runtime, Checkpoint,
    erforderliche Source, Source-`.git_commit`-/Git-Checkout-Metadaten oder
    Options-Sidecar nicht erreichbar sind, schlägt der Befehl eindeutig fehl
    und fällt nicht auf eine normale Font zurück.
  - Die standardmäßige isolierte Runtime ist das Docker-Image
    `injection-scrabblegan`; `--handwriting-runtime-command` ist ein expliziter
    Override für Host-Tests oder eine andere isolierte Runtime.
  - Der eigenständige Befehl ist `uv run injection-pipeline
    generate-handwriting --seed <seed>` und schreibt dasselbe wiederverwendbare
    Bundle wie die integrierte Injektion.
  - Normale Asset-Erzeugung verwendet CPU-only-Inferenz in der isolierten
    Runtime. Auf dem Rechner, der die Injektions-Pipeline ausführt, ist keine
    GPU erforderlich.
  - Da das offizielle Amazon-Repository zwar Trainings- und Generierungscode,
    aber keinen einsatzbereiten Generator-Checkpoint enthält, verwendet v1
    einen aus dem offiziellen Code trainierten Checkpoint. Das Training ist
    eine einmalige Voraussetzung auf einer Universitäts- oder Cloud-GPU; der
    trainierte Generator wird anschließend für CPU-Inferenz eingebunden.

Durch die Review bestätigt; an den mit *(offen)* markierten Stellen in WP0 erneut
zu validieren:

- **Inferenz läuft im Container auf der CPU.** Die Wortbild-Erzeugung mit dem
  trainierten Generator ist günstig; CPU-Inferenz beseitigt das Problem des
  CUDA-9/10-Basis-Images, das Risiko entfernter Docker-Hub-Tags und die
  Unsicherheit der WSL2-GPU-Durchleitung auf der Windows-Entwicklungsmaschine.
  Sie ist deterministischer als CUDA. Eine GPU wird nur für das *Training*
  benötigt, das außerhalb des Container-Repositories läuft (Universitäts-GPU
  oder Colab).
- **Der Wrapper lädt einen rohen `net_G`-State-Dict aus einer einzelnen
  eingebundenen Datei.** Dadurch bleibt der bestehende Vertrag
  `--checkpoint` + `--checkpoint-sha256` erhalten. Der Trainingslauf muss
  `latest_net_G.pth` exportieren; der Wrapper rekonstruiert die
  Generatorarchitektur aus festgelegtem Upstream-Code und einem kleinen
  JSON-Sidecar mit Architekturoptionen (Alphabet, Bildhöhe, Kanäle).
- **Upstream-Source bleibt ein Runtime-Mount** (festgelegter Commit über
  `.git_commit`) und wird weder vendored noch versioniert – unverändert zum
  aktuellen Design.
- **Datensatz/Alphabet: IAM, `IAMcharH32rmPunct`.** Englische Wörter ohne
  Interpunktion. Ziffern/Bindestriche in `patient_id`/`accession_number` und
  Umlaute in Namen müssen daher gegen das tatsächliche Checkpoint-Alphabet
  validiert und zurückgewiesen werden (v1: zurückweisen, nicht transliterieren).
  *(offen – IAM-Zugangsregistrierung und Vorkommen von Ziffern im trainierten
  Alphabet bestätigen)*
- **Mehrwortwerte von `patient_name` werden wortweise gerendert und
  horizontal zusammengesetzt**; das Batch-Tool verwendet einen festen,
  seed-basierten Abstand, das Manifest-`text` behält die vollständige
  Zeichenkette. Eine pauschale Zurückweisung von Leerzeichen würde
  `patient_name` unbrauchbar machen.
- Den Checkpoint-/Inferenzvertrag nach Bestätigung der WP0-Entscheidungen als
  **ADR-0010** festhalten (passt in die bestehende Reihe unter
  `docs/decisions/`).

## Arbeitspakete

Jedes WP enthält Akzeptanzkriterien als Checkboxen. Diese werden beim Abschluss
aktualisiert und die Statuszeile am Anfang wird angepasst. Fehlgeschlagene
Ansätze nicht löschen, sondern durchstreichen und dokumentieren, wodurch sie
ersetzt wurden.

## Einmalige Voraussetzung für den Benutzer

Der Benutzer muss die Modellintegration nicht manuell implementieren; vor der
Verwendung von `--font-family handwriting` für echte Assets muss jedoch ein
trainierter Generator-Checkpoint vorhanden sein. Die Einrichtung folgt dem
offiziellen Amazon-Repository:

1. Den festgelegten Commit von
   `https://github.com/amzn/convolutional-handwriting-gan` in einem separaten
   Linux-/WSL2- oder Cloud-GPU-Arbeitsbereich clonen.
2. Für IAM registrieren und den Datensatz laden, anschließend die offizielle
   Struktur `Datasets/IAM` (`wordImages`, `lineImages`, `original` und
   `original_partition`) einrichten. Den Datensatz außerhalb von Git und
   versionierten Projekt-Fixtures halten.
3. Die offizielle Legacy-Umgebung aus `environmentPytorch12.yml` erstellen;
   das Repository dokumentiert Python 3.6, PyTorch 1.2, CUDA 9 und Ubuntu 16.04
   als getestete Kombination.
4. Den offiziellen Vorbereitungsschritt `data/create_text_data.py` ausführen
   und das resultierende Alphabet vor dem Training prüfen. Der Checkpoint muss
   die für die drei sichtbaren Prototype-Felder benötigten Buchstaben, Ziffern
   und den Bindestrich unterstützen; andernfalls müssen Trainingsdaten oder
   Konfiguration vor der Integration erweitert werden.
5. Mit dem offiziellen Workflow `train.py`/`train_semi_supervised.py` auf der
   externen GPU trainieren, Generatorgewichte und Architekturoptionen
   exportieren und den Checkpoint unter dem ignorierten Verzeichnis
   `DicomData/HandwritingAssets/scrabblegan/checkpoints/` ablegen.

Die Repository-Implementierung baut anschließend die isolierte Runtime,
validiert den Checkpoint-Hash, startet automatisch die CPU-Inferenz und
erzeugt bzw. cached die angeforderten Seed-Assets. Kein Checkpoint, keine IAM-
Daten und keine Legacy-Umgebung werden zum Python-3.13-Projekt hinzugefügt.

### WP0: Entscheidungen und Voraussetzungen

Die oben genannten *(offen)* Entscheidungen bestätigen und die externen
Voraussetzungen sichern.

- [ ] Den exakten Upstream-Commit festlegen (in diesem Plan und in den
      Dokumenten zur `.git_commit`-Konvention festhalten).
- [x] Bestätigt: CPU-only-Inferenz ist für v1 ausreichend; die GPU ist für das
      einmalige Checkpoint-Training reserviert.
- [ ] Zugriff auf den IAM-Datensatz erhalten (Registrierung) und unter
      `DicomData/` gespeichert (von Git ignoriert); Lexikondateien geladen.
- [x] Trainingsort festgelegt: externe Linux-GPU, vorzugsweise eine
      Universitätsmaschine; eine Cloud-GPU ist der Fallback. Der Checkpoint
      wird nicht in der Python-3.13-Projektumgebung trainiert.
- [x] Renderer-Vertrag festgelegt: eine gemeinsame Font-/Renderer-Auswahl mit
      `arial`, `calibri`, `tahoma`, `consolas` und `handwriting`.
- [x] Handschriftumfang auf die sichtbaren Felder beschränkt:
      `patient_name`, `patient_id` und `accession_number`.
- [x] Cache-Identität umfasst Seed, Schema, Feld, erzeugten Text, Checkpoint,
      Upstream-Commit, Generator-Manifest-Hash und Options-Sidecar-Hash;
      die Invalidierung ist explizit.
- [x] Eigenständiger Befehl ist `generate-handwriting --seed <seed>` und teilt
      den Vertrag des integrierten Asset-Providers.
- [x] Fehlende oder nicht erreichbare ScrabbleGAN-Voraussetzungen lassen den
      Lauf fehlschlagen; es gibt keinen automatischen Font-Fallback.
- [ ] ADR-0010 mit dem Checkpoint-/Inferenzvertrag entworfen.

### WP1: Container-Neuaufbau

Das fehlerhafte Dockerfile (Review-Ergebnis 2) durch eines ersetzen, das den
Upstream-Code tatsächlich ausführt.

- Basis: Für CPU-Inferenz ist kein normales `ubuntu:16.04`-kompatibles Image
  erforderlich; eine schlanke Linux-Basis + **Micromamba** verwenden und die
  Umgebung aus Upstreams `environmentPytorch12.yml` erstellen (PyTorch-1.2.0-
  CPU-Build-Variante, falls der CUDA-Pin der YML unter CPU fehlschlägt – die
  Abweichung anpassen und dokumentieren).
- Die Einstiegspunkte `scrabblegan-render` / `scrabblegan-validate` behalten,
  nun innerhalb der Micromamba-Umgebung ausgeführt.
- Den Micromamba-Solver statt des Legacy-Conda-Solvers verwenden; letzterer
  kann beim Auflösen des historischen Python-3.6-Abhängigkeitsgraphen den für
  Docker Desktop verfügbaren Speicher erschöpfen.
- Tote `PYTORCH_VERSION`-/CUDA-ARGs entfernen oder tatsächlich verwenden.

- [x] `docker build` ist aus einem sauberen Checkout erfolgreich.
- [x] Container-Smoke-Test erfolgreich: `python -c "import torch, torchvision;
      print(torch.__version__)"` gibt 1.2.0 aus und Upstream-Imports aus
      `models/` funktionieren gegen einen eingebundenen Source-Checkout.
- [x] `scrabblegan-render --help` / `scrabblegan-validate --help` funktionieren
      (aktueller CMD-Vertrag erhalten).

### WP2: Beschaffung des Checkpoints

Upstream veröffentlicht keine Gewichte (Review-Ergebnis 3); einmal außerhalb
des Containers trainieren.

- Dem Upstream-README folgen: `data/create_text_data.py` → LMDB → `train.py`
  mit `IAMcharH32rmPunct`.
- `latest_net_G.pth` und den JSON-Sidecar mit Architekturoptionen exportieren,
  SHA-256 berechnen und unter
  `DicomData/HandwritingAssets/scrabblegan/checkpoints/`.

- [ ] Trainingslauf abgeschlossen; Beispielrasterbilder visuell plausibel.
- [ ] `model.pth` (= exportierter `net_G`) + Options-Sidecar + SHA-256
      aufgezeichnet (der Hash gehört in Run-Befehle, nicht als falscher
      `PIN_...`-Platzhalter in versionierte Dokumente).
- [ ] Trainierte Alphabetzeichenkette extrahiert und aufgezeichnet (Eingabe für
      die WP4-Validierung).

### WP3: Single-Text-Inference-Wrapper

Der zentrale fehlende Baustein (Review-Ergebnis 1): ein Skript, das eine
Textzeichenkette deterministisch in eine PNG-Datei rendert.

- Speicherort: `tools/handwriting/scrabblegan/wrapper/generate_single.py`, in
  das Image neben `scrabblegan_tool` kopiert (es gehört uns, anders als die
  eingebundene Upstream-Source). Python-3.6-kompatibel.
- Vertrag:
  `--text --seed --checkpoint --options-json --output --source-dir` — passend
  zu den bestehenden `--generator-command`-Platzhaltern und dem
  Provider-Sidecar-Pfad `--handwriting-options-json`.
- Verhalten: `random`/`numpy`/`torch` seeden (+
  `torch.backends.cudnn.deterministic`, falls jemals eine GPU verwendet wird),
  `netG` aus festgelegtem Upstream-Code in `models/` aufbauen, State-Dict laden,
  Text über das Alphabet codieren, generieren und ein Graustufen-PNG speichern.
- Diesen Wrapper als eingebauten Standardbefehl in `render.py` verwenden (den
  fiktiven `generate.py`-Standard ersetzen).

- [ ] Wrapper rendert ein bekanntes Wort im Container in ein PNG.
- [ ] Derselbe Seed + Text + Checkpoint → bei wiederholten Läufen byte-
      identisches PNG (Determinismusvertrag, AGENTS.md).
- [ ] Unterschiedliche Seeds → sichtbar unterschiedliche Handschrift.
- [x] Eingabe außerhalb des Alphabets schlägt mit eindeutigem Fehler fehl
      (keine unbrauchbare Ausgabe).
- [x] Standardbefehl in `render.py` aktualisiert; README-Befehlsbeispiele in
      WP7 aktualisiert.

### WP4: Korrekturen am Batch-Tool

Die Tool-Ergebnisse beheben, damit echte (Graustufen-, Alpha-lose)
Generatorausgabe korrekt verarbeitet wird.

- `masks.py`: Tintenmaske aus dem White-Distance-Schwellwert ableiten, wenn das
  Rohbild keinen sinnvollen Alpha-Kanal besitzt; `background` nur für das
  Compositing verwenden (Review-Ergebnis 4). Die Pixel-Schleife dabei durch
  `Image.point`/numpy ersetzen (Ergebnis 6b).
- `manifest.py`: `text` gegen das Checkpoint-Alphabet validieren (als
  Datei/Option übergeben); `ink_color: white` + `background: white`
  zurückweisen (Ergebnis 6a).
- Mehrwortunterstützung: an Leerzeichen teilen, jedes Wort über den Wrapper
  rendern und mit festem Abstand im Batch-Tool zusammensetzen.

- [x] Assets mit transparentem Hintergrund erzeugen aus einem echten
      Graustufen-Rohbild eine korrekte Maske (kein Vollrechteck) – abgedeckt
      durch einen Unit-Test mit synthetischem Graustufen-Rohbild.
- [x] Die Alphabetvalidierung weist fehlerhafte Datensätze beim Manifest-Laden
      mit Zeilennummern zurück; Weiß auf Weiß wird zurückgewiesen.
- [x] Mehrwort-Rendering erzeugt ein Bild + eine Maske + eine Bounding-Box pro
      Asset; der Wortabstand ist deterministisch.
- [x] Bestehende Fake-Renderer-Tests bleiben unverändert erfolgreich
      (Vertragsstabilität).

### WP5: End-to-End-Lauf und Injektion

Die Provider-/Cache-Verdrahtung auf dem Host ist für integrierte Injektion und
eigenständige Generierung implementiert. Der reale Docker-/Upstream-
Checkpoint-Lauf wurde am 2026-07-15 erfolgreich abgeschlossen.

- Einen realen Batch-Lauf im Container gegen den trainierten Checkpoint für
  alle drei v1-Felder (einschließlich Mehrwortname).
- `scrabblegan-validate` für das Ausgabemanifest.
- `uv run injection-pipeline --handwriting-manifest ... --handwriting-asset
  patient_name=...` verwendet die Assets.
- Integrierter Handschriftlauf: Nach Festlegung von Seed und gemeinsamer
  Font-/Renderer-Auswahl die Faker-Identität erzeugen, das Asset-Bundle des
  Seeds auflösen oder erstellen, passende Assets an jedes ausgewählte
  Render-Element hängen und das resultierende Manifest unter
  `DicomData/HandwritingAssets/` persistieren.
- Eigenständiger Seed-Lauf: den Asset-Provider ohne Dokument aufrufen und
  dasselbe Bundle und Manifest schreiben, das der integrierte Lauf
  wiederverwenden würde.

- [x] Batch-Lauf abgeschlossen; `failures.jsonl` leer oder begründet.
- [x] Ausgabemanifest besteht die Validierung (Hashes, Bounding-Boxen, relative
      Pfade).
- [x] Injektionslauf erzeugt ein DICOM/eine Preview mit visuell korrektem
      Handschrift-Overlay (Position, Tintenfarbe, Transparenz) – Screenshot
      oder Preview-Artefakt liegt unter der Run-Ausgabe.
- [x] Ground Truth des Injektionslaufs zeichnet das Handschrift-Asset
      (`renderer_type: handwriting_asset`) korrekt auf.
- [x] Eine zweite Injektion mit demselben aufgelösten Seed und kompatiblem
      Cache-Schlüssel verwendet die vorhandenen Assets erneut und ruft
      ScrabbleGAN nicht nochmals auf.
- [x] Eigenständiger Seed-Befehl und integrierter Lauf erzeugen kompatible
      Asset-Manifeste und deterministische Bild-/Masken-Hashes.

### WP6: Tests

Die in WP3–WP5 eingeführten Bestandteile in die wiederholbar ausführbare
Testsuite zusammenführen.

- Hostseite (Python 3.13, bestehendes Muster
  `tests/unit/test_scrabblegan_generator.py`): neue Tests für Alphabet-
  validierung, Zurückweisung von Weiß auf Weiß, Maskenableitung aus
  Graustufen-Rohdaten, Mehrwort-Compositing und das Erzeugen des
  `--generator-command`-Templates.
- Containerseite: ein unter `tools/handwriting/scrabblegan/` versioniertes
  Smoke-Test-Skript, das Fake-Renderer und einen realen Render-Lauf mit einem
  Datensatz ausführt und die Manifestgültigkeit prüft – manuell ausführbar und
  dokumentiert, aber nicht in CI verdrahtet (CI besitzt keinen Checkpoint).
- Determinismus: prüfen, dass zwei Render-Läufe desselben Datensatzes
  identische `image_sha256`/`mask_sha256` liefern (realer Renderer manuell,
  Fake-Renderer in CI).
- Cache-Verhalten: Ein Cache-Hit vermeidet Generierung; ein Cache-Miss erzeugt
  alle erforderlichen Assets; veraltete/inkompatible Cache-Einträge folgen der
  dokumentierten Invalidierungsrichtlinie.
- CLI-Verhalten: Interaktive Prompts fragen die gemeinsame Font-/Renderer-
  Auswahl direkt nach dem Seed und vor den übrigen Render-Parametern ab; die
  eigenständige Generierung akzeptiert einen Seed und schreibt das erwartete
  Asset-Bundle.

- [x] `uv run pytest tests/unit/test_scrabblegan_generator.py -q` erfolgreich:
      17 Tests bestanden am 2026-07-15, einschließlich JSON-/JSONL-
      Manifestverarbeitung.
- [x] `uv run ruff check src/ tests/` / `uv run mypy src/` erfolgreich am
      2026-07-15 (Tool-Code bleibt bis auf die Provider-Schnittstelle außerhalb
      von `src/`).
- [ ] Das vollständige Gate `uv run pytest tests/ -x` ist unter Windows
      erfolgreich. Einige umfangreichere pytest-Fälle sind derzeit durch
      Berechtigungsfehler beim Erzeugen temporärer Windows-Verzeichnisse
      blockiert; nach Behebung dieses Umgebungsproblems erneut ausführen.
- [x] Container-Smoke-Test dokumentiert und einmal mit dem echten Checkpoint
      ausgeführt; Ergebnis hier festgehalten.

### WP7: Dokumentation und Planabschluss

- `tools/handwriting/scrabblegan/README.md` aktualisieren: reale
  Voraussetzungen (Training erforderlich, keine vortrainierten Gewichte),
  Wrapper als Standard-Generatorbefehl, reale (nicht-fiktive) Befehlsbeispiele,
  CPU-Inferenzhinweis sowie Alphabet-/Mehrwortregeln.
- `UPSTREAM_REVIEW.md` aktualisieren: jedes Ergebnis mit Verweis auf
  korrigierendes WP/Commit als gelöst markieren; die Datei als historischen
  Datensatz erhalten.
- ADR-0010 abschließen (accepted).
- Beispielmanifeste in `examples/` aktualisieren, falls der Vertrag Felder
  hinzugewonnen hat (z. B. Verweis auf Options-Sidecar).
- `docs/dicom-injection.md`, `README.md` und die Architektur-/Arbeitspaket-
  Dokumente mit integriertem Renderer-Modus, Cache-Verhalten, interaktiver
  Prompt-Reihenfolge und eigenständigem Befehl aktualisieren.

- [x] README neu geschrieben und konsistent mit dem implementierten Verhalten
      auf dem Host.
- [ ] Alle Ergebnisse in UPSTREAM_REVIEW als gelöst/zurückgestellt markiert.
- [ ] ADR-0010 angenommen und querverlinkt.
- [ ] **Dieser Plan: alle Checkboxen aktiviert, Statuszeile auf `done` mit
      Datum gesetzt.** Nicht aktivierte Punkte müssen einen schriftlichen Grund
      (zurückgestellt/verschoben) tragen.

## Testszenarien (Zusammenfassung)

1. Fake-Renderer-Roundtrip (bestehend) – Regression-Schutz für den Vertrag.
2. Graustufen-Rohdaten + `transparent`-Hintergrund → korrekte Maske und
   Bounding-Box.
3. Alphabet: Datensatz mit Zeichen außerhalb des Alphabets wird beim Laden
   zurückgewiesen.
4. Weiße Tinte auf weißem Hintergrund wird zurückgewiesen.
5. Mehrwortname → einzelnes zusammengesetztes Asset, deterministischer Abstand.
6. Determinismus: identischer Datensatz zweimal gerendert → identische Hashes.
7. End-to-End: echtes Manifest → Rendern → Validieren → Injizieren → visuelle
   Prüfung.
8. Integrierter Cache: Seed → Faker-Identität → Generierung bei Cache-Miss →
   Injektion → persistiertes Asset-Bundle → Cache-Hit beim Wiederholungslauf.
9. Auf eigenständige Seed-Generierung folgende Injektion verwendet das
   erzeugte Bundle ohne erneute Generierung.

## Validierungsbefehle

```powershell
# Tests auf dem Host
uv run pytest tests/ -x
uv run ruff check src/ tests/
uv run mypy src/

# Fokussierte Handschriftvalidierung vom 2026-07-15
uv run pytest tests/unit/test_handwriting*.py tests/unit/test_scrabblegan_generator.py

# Container-Build + Smoke-Test
docker build --platform linux/amd64 -t injection-scrabblegan tools/handwriting/scrabblegan
docker run --rm --platform linux/amd64 injection-scrabblegan

# Echtes Rendering + Validierung + Injektion (verifiziert am 2026-07-15):
uv run injection-pipeline generate-handwriting --seed 42
uv run injection-pipeline --seed 42 --font-family handwriting
```

## Risiken und Hinweise

- **Lokale Voraussetzungen sind vorhanden und verifiziert.** Offizielle
  Source, `.git_commit`, Checkpoint, Begleit-Checkpoints und Options-Sidecar
  liegen bereits unter dem ignorierten Baum `DicomData/HandwritingAssets/`.
  Auf einem anderen Rechner müssen sie in derselben Struktur bereitgestellt
  werden; IAM-Daten, Checkpoints, erzeugte Assets oder externe Source nicht in
  versionierte Repository-Pfade kopieren.
- **Training bleibt extern, wenn der Checkpoint ersetzt wird.** IAM-
  Registrierung, LMDB-Vorbereitung und GPU-Training sind für die aktuelle
  Inferenz-Einrichtung nicht erforderlich, werden aber zum Training eines
  neuen kompatiblen Modells benötigt.
- **PyTorch-1.2.0-CPU-Verfügbarkeit ist verifiziert.** Das Micromamba-Image
  baut und führt die festgelegte Python-3.6-/PyTorch-1.2-CPU-Umgebung aus; für
  Handschriftgenerierung ist kein CUDA-Image erforderlich.
- **Handschriftrealismus** für ziffernlastige Felder hängt davon ab, dass
  Ziffern im IAM-Trainingsalphabet enthalten sind. Andernfalls benötigen
  `patient_id`/`accession_number` möglicherweise ein ziffernfähiges Retraining
  oder müssen für v1 zurückgestellt werden (Entscheidungspunkt in WP0/WP2).
- Alter Upstream-Code kann kleine Kompatibilitätspatches benötigen; solche
  Patches als dokumentierte `.patch`-Dateien im Tool-Verzeichnis ablegen und
  auf die eingebundene Source anwenden – niemals stillschweigend forken.
