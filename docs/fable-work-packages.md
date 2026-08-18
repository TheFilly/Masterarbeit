# Fable-Arbeitspakete — zweite Generation

Backlog der Arbeitspakete nach der abgeschlossenen Architekturabgleich-Runde.
Die erste Generation (WP-A bis WP-H) wurde am 2026-07-06 ausgeführt und aus
dieser Datei entfernt; ihre Ergebnisse liegen in `docs/architecture/` und
`docs/decisions/` (ADR-0001..0009). Der DICOM/JPG-Implementierungslauf am
2026-07-12 schloss WP-I sowie die zentralen WP-B..WP-G-Übergabestücke ab. WP-P
und zwei von drei WP-R-Punkten folgten am 2026-07-13. Verbleibende Arbeit bleibt
unten ausdrücklich aufgeführt.

| Paket | Status der Ergebnisse |
|---|---|
| WP-A | Blueprint und ADR-Review in `docs/architecture/target-architecture.md` festgehalten. |
| WP-B | Für DICOM/JPG implementiert: pydantic-Modelle, `RunRecord` und Round-Trip-Tests. Gemeinsame Geometrie- und PDF-Sidecar-Modelle sind implementiert; breitere PDF-Fixture-Abdeckung bleibt offen. |
| WP-C | Für DICOM/JPG implementiert: Identifier-Schema-Loader, Standardschema, schema-gesteuerte Identitätsgenerierung und Planung. Verbleibend: Ausgabe der Schema-Provenienz nach ADR-0008. |
| WP-D | Für DICOM/JPG implementiert: Runner-Aufteilung, `RunRecord`-Verkabelung und Adapterauflösung. PDF-Adapter-CLI-Integration gemäß freigegebenem PDF-Plan implementiert; breitere operative Fixture-Abdeckung bleibt offen. |
| WP-E | Für DICOM/JPG implementiert: mypy-Override entfernt, Engine aufgeteilt, tote API entfernt, DICOM-Pixel-Schreiben verschoben. Verbleibend: keine DICOM/JPG-Kern-Typisierungsarbeit nach WP-P. |
| WP-F | Für DICOM/JPG implementiert: Adaptermodelle, Registry, DICOM/JPG-Loader und -Writer. Das PDF-Loader/Writer-Paar ist gemäß freigegebenem PDF-Plan implementiert; breitere operative Fixture-Abdeckung bleibt offen. |
| WP-G | Teilweise implementiert: geseedeter Default-Input, injizierbare Uhr, stabile Seed-Ableitung, deterministisches `reference_date`. Verbleibend: Ausgabe von Umgebung/Provenienz nach ADR-0008. |
| WP-H | Abgeschlossen: Die aktive Dokumentation hängt nicht mehr von der ausgemusterten Research/Thesis/Templates-Schicht ab. |

Grundregeln für die folgenden Pakete:

- Als **Design** markierte Pakete erzeugen Markdown-Ergebnisse unter `docs/`
  (Fables Aufgabe); als **Implementierung** markierte Pakete werden von
  Opus/Codex direkt anhand einer bestehenden Spezifikation mit Tests ausgeführt.
- Konkreten Code referenzieren (`file:line`); Design-Ergebnisse enden mit einer
  Implementierungsübergabe und einem Abschlusskriterium.
- Die Migrationsinvariante bewahren: Bestehende DCM/JPG-Runs bleiben
  byteidentisch, sofern kein ADR eine Änderung genehmigt
  (`docs/dicom-injection.md`, Validierungsstatus).
- Die Thesis-Traceability-Schicht (Claims, Findings, Templates) wurde am
  2026-07-06 entfernt und liegt außerhalb des Umfangs aller Pakete.

---

## WP-I — End-to-End-Test-Harness und CI (Implementierung, abgeschlossen 2026-07-12)

**Implementiert.** `tests/fixtures/synthetic_documents.py` erzeugt synthetische
DCM/JPG-Eingaben ohne reale oder aus MIMIC abgeleitete Daten.
`tests/integration/test_end_to_end.py` führt DICOM- und JPG-Pfade mit festem
Seed, festem Input, festem Zeitstempel, Standardschema und deterministischer
Testschrift aus und vergleicht anschließend alle Artefakt-Hashes. Die CI in
`.github/workflows/ci.yml` führt uv sync, ruff, mypy und pytest aus.

**Verbleibend.** Nichts für WP-I. Der Ein-Pixel-Nachweis aus dem Scratch-Branch
wird nicht als Repository-Artefakt aufbewahrt.

---

## WP-J — ScrabbleGAN-Neustart und Injektionsintegration (Implementierung, Abschluss offen)

**Ziel.** Echte ScrabbleGAN-Handschriftgenerierung in diesem Repository von
Anfang bis Ende nutzbar machen: eine ausführbare Umgebung, ein funktionierender
Inference-Pfad für Einzeltexte, ein festgelegter Checkpoint sowie erzeugte
Assets, die über den bestehenden Manifestvertrag in einen Injektions-Run
fließen. Den Batch-Vertrag so erweitern, dass die Injektionspipeline fehlende
Assets nach der Faker-Identitätsgenerierung erzeugen, aus
`DicomData/HandwritingAssets/` wiederverwenden und dasselbe Verhalten über einen
eigenständigen seed-basierten Konsolenbefehl anbieten kann.

**Warum jetzt.** Der erste Versuch erzeugte ein solides Batch-Grundgerüst
(`tools/handwriting/scrabblegan/`: Manifestvertrag, Hashing, Validierung,
Fake-Renderer), aber keine echte Generierung. `UPSTREAM_REVIEW.md` (2026-06-11)
stellte fest, dass die Integration gegen eine angenommene Upstream-Schnittstelle
gebaut war, die nicht existiert. Das Grundgerüst soll erhalten bleiben; der
Generierungskern muss auf der verifizierten Upstream-Realität
(`https://github.com/amzn/convolutional-handwriting-gan`).

**Zu beseitigende verifizierte Blocker (aus `UPSTREAM_REVIEW.md`, vor dem Build
gegen Upstream-`master` erneut bestätigen):**

1. **Keine Inferenz für Einzeltexte im Upstream.** `render.py:89-106` verwendet
   standardmäßig einen fiktiven Aufruf `generate.py --text ... --seed ...
   --checkpoint ... --output ...`; Upstream besitzt nur
   `generate_wordsLMDB.py` (Lexikon-Sampling, LMDB/TIFF-Ausgabe, kein Seed-Flag,
   Laden über `TestOptions`/`create_model()` im Pix2pix-Stil). Ein eigener
   Wrapper (`generate_single.py`) muss in diesem Repository geschrieben werden:
   Options-Objekt aufbauen, `netG`-Gewichte laden, Text mit dem Datenalphabet
   kodieren, `torch`/`numpy`/`random` aus dem Manifest-Seed seeden und eine PNG
   nach `--output` schreiben.
2. **Das Docker-Image kann ScrabbleGAN nicht ausführen.** `Dockerfile:6`
   verwendet CUDA 9.0 / Ubuntu 16.04, installiert nur `Pillow<8`
   (`Dockerfile:33`), installiert PyTorch nie, und
   `apt-get install python3.6` schlägt unter Xenial fehl. Upstream benötigt
   Python 3.6.8 + PyTorch 1.2.0 + cudatoolkit 10.0
   (`environmentPytorch12.yml`); alte `nvidia/cuda`-Tags könnten aus Docker Hub
   entfernt worden sein.
3. **Es gibt keine vortrainierten Gewichte.** Upstream veröffentlicht keine;
   ein Checkpoint muss lokal auf IAM/RIMES/CVL trainiert (manuelle
   Dataset-Registrierung) oder aus einer Community-Reproduktion bezogen und per
   Hash festgelegt werden. Der einzelne `model.pth`-Mount des Toolings passt
   außerdem nicht zu Upstreams Layout
   `<checkpoints_dir>/<experiment>/<epoch>_net_G.pth` — es ist zu entscheiden,
   ob der Wrapper direkt ein rohes `net_G.pth`-State-Dict lädt.
4. **Maskenfehler bei echter Ausgabe.** `masks._build_mask` vertraut bei
   `background == "transparent"` auf den Alphakanal, aber echte ScrabbleGAN-
   Ausgabe ist Graustufenbild ohne Alpha — nach `convert("RGBA")` ist jedes
   Pixel opak und die Maske wird zu einem soliden Rechteck. Tinte immer aus dem
   Abstand-zu-Weiß-Schwellenwert ableiten; Alpha nur verwenden, wenn das
   Rohbild einen nichttrivialen Alphakanal besitzt.
5. **Alphabetbeschränkungen werden nicht validiert.** Trainierte Alphabete (z. B.
   `IAMcharH32rmPunct`) können Ziffern/Bindestriche ausschließen — Werte von
   `patient_id` (`SYNTH-######`) und `accession_number` können unbrauchbare
   Glyphen erzeugen; mehrteiliger `patient_name` benötigt Generierung pro Wort
   und anschließendes Compositing. `manifest.py` soll `text` gegen das
   Checkpoint-Alphabet validieren; die Strategie für mehrere Wörter ist zu
   definieren.
6. **Kleinigkeit:** `ink_color: white` + `background: white` ablehnen; die
   Python-Pixel-Schleife in `masks._build_mask` durch numpy ersetzen.

**Phase 0 — Machbarkeitsentscheidung (Design, ein ADR).** Vor Änderungen am
Dockerfile die Runtime-Strategie entscheiden; dies war die entscheidende Lücke
des ersten Versuchs. Optionen anhand des tatsächlichen Hosts (Windows 10 + WSL2
+ GPU-Verfügbarkeit) bewerten:

- (a) Getreuer Legacy-Container: Miniconda + Upstream-
  `environmentPytorch12.yml` in einer CUDA-10.0-Basis — maximale Treue,
  fragile Verfügbarkeit des Basis-Images, GPU-Durchreichung über WSL2 für das
  Training erforderlich.
- (b) **Portierung auf modernes PyTorch (empfohlener Standard):** Upstream-
  Inferenzcode mit aktuellem PyTorch in einem einfachen Container oder venv
  ausführen; Code aus der Pix2pix-Ära benötigt typischerweise kleine Patches.
  CPU-Inferenz reicht für die Asset-Erzeugung, nur das Training benötigt die GPU.
- (c) ScrabbleGAN durch ein gepflegtes Handschrift-Synthesemodell mit
  veröffentlichten Gewichten ersetzen — Fallback, falls (a) und (b) das
  Zeitbudget überschreiten; Manifest-/Masken-/Validierungsvertrag sind bewusst
  generatoragnostisch, daher ändert sich nur der Befehl von `render.py`.

Das ADR muss außerdem den Checkpoint-Plan (Training versus Community-Gewichte,
Lizenzbedingungen der Datensätze — IAM erfordert Registrierung und darf nie
eingecheckt werden) festlegen und den Upstream-Commit pinnen
(`Dockerfile:9` enthält noch `PIN_UPSTREAM_COMMIT`).

**Implementierungsreihenfolge (nach dem ADR).**

1. Upstream-Commit pinnen; `generate_single.py` darauf schreiben (Blocker 1)
   und als eingebauten Standardbefehl in `render.py` verwenden, der den
   fiktiven `generate.py`-Pfad ersetzt.
2. Gewählte Runtime bauen (Blocker 2 oder Portierungsalternative);
   `generate_single.py` mit zufällig initialisierten Gewichten einem
   Smoke-Test unterziehen (Shape-/Alphabet-Verkabelung funktioniert ohne
   trainierten Checkpoint).
3. Checkpoint gemäß ADR beschaffen/trainieren; SHA-256 aufzeichnen; die
   Trainingsvoraussetzung im README dokumentieren (Blocker 3).
4. Maskenableitung (Blocker 4) und kleinere Korrekturen (Blocker 6) beheben;
   Fake-Renderer-Tests um ein Alpha-freies Graustufen-Fixture erweitern, das
   den Fehler zunächst reproduziert.
5. Alphabetvalidierung und Strategie für mehrere Wörter ergänzen (Blocker 5);
   `examples/batch_manifest.example.jsonl` entsprechend aktualisieren.
6. Ende zu Ende: `batch.jsonl` → echtes Rendering → `manifest.jsonl` →
   `scrabblegan-validate` → `uv run injection-pipeline --handwriting-manifest
   ... --handwriting-asset patient_name=...` erzeugt einen DCM-Run mit korrekter
   Tintenmaskengeometrie in `ground_truth.json`.
7. Befunde in `UPSTREAM_REVIEW.md` als gelöst/überholt umschreiben; die
   „blocked“-Hinweise in beiden READMEs aktualisieren.

**Umfang / DoD.** Ein echtes erzeugtes Asset für jedes ausgewählte v1-Feld
(`patient_name`, `patient_id`, `accession_number`, sofern die Feldentscheidung
die Menge nicht erweitert) wird in einen DCM-Run injiziert; ein zweiter Run mit derselben kompatiblen
Seed-/Cache-Identität verwendet die gespeicherten Assets wieder; ein
eigenständiger Seed-Befehl erzeugt dasselbe wiederverwendbare Bundle; bestehende
Fake-Renderer-Tests bleiben erfolgreich; keine Legacy-Abhängigkeiten gelangen
in das Python-3.13-Projekt (`tools/handwriting/README.md`-Runtime-Grenze bleibt
erhalten); keine Datensätze, Gewichte oder erzeugten Assets werden eingecheckt.

**Abhängigkeiten.** Der echte Generierungskern bleibt isoliert, aber die
integrierte Asset-Provider-Grenze berührt Runtime-CLI, Runner, Render-Plan und
Ground-Truth-Metadaten der Hauptpipeline. **Hebel.** Hoch für Datensätze, die
realistische Handschrift benötigen; das bestehende Grundgerüst reduziert die
Integrationsarbeit, nicht aber das Risiko bei Modell/Checkpoint oder
Cache-Vertrag.

---

## WP-K — DICOM-Konformität und Validatoren (Design)

**Ziel.** Das Modul `validators/` und die DICOM-Konformitätsrichtlinie für
injizierte Ausgaben spezifizieren.

**Warum jetzt.** `writers/dicom.py` generiert `SOPInstanceUID` nach einer
Änderung der Pixeldaten nicht neu und schreibt die Transfer Syntax in
ExplicitVRLittleEndian um. Nachgelagerte Konsumenten könnten solche Dateien
ablehnen oder falsch indizieren. Für `validators/` gibt es noch keine
implementierte Validierungsrichtlinie.

**Ergebnisse.** `docs/architecture/validators-spec.md`: Validierungsstufen
(Schema-Round-Trip, Konsistenz von Annotation und Geometrie gegenüber den
gerenderten Pixeln, Formatgültigkeit pro Adapter) sowie ein ADR zur UID-
Neugenerierung und Transfer-Syntax-Richtlinie (ein bewusster
Bytekompatibilitätsbruch, daher mit eigenem Golden-File-Übergangsplan).

**Abhängigkeiten.** WP-B-Modelle implementiert; WP-I-Harness. **Hebel.** Mittel
bis hoch.

---

## WP-L — Multi-Frame-Injektionsrichtlinie (klein, Design)

**Ziel.** Entscheiden und festhalten, wie Multi-Frame-DICOM (Cine-Loops)
injiziert werden soll.

**Warum jetzt.** Nur Frame 0 wird injiziert (`applied_frame_indices: [0]` in
`engine/injector.py`); ein Loop mit 47 Frames ist auf 46 Frames PII-frei. Für
Detektor-Trainingsdaten ist dies eine Datensatzeigenschaft, die behoben oder als
beabsichtigt dokumentiert werden muss.

**Ergebnisse.** Ein ADR (alle Frames injizieren versus nur Frame 0 als
aufgezeichnete Eigenschaft versus Option pro Run) sowie die Ground-Truth-
Auswirkungen (`frame_index`-Semantik in `BoxAnnotation`, Ecken pro Frame) als
Nachtrag in die WP-B-Spezifikation übernehmen.

**Abhängigkeiten.** WP-B-Spezifikation (Annotationsformen). **Hebel.** Mittel.

---

## WP-M — Batch-Generierungsmodus (Design)

**Ziel.** Den Runner für Datensatzgröße entwerfen: viele Dokumente pro Aufruf
mit abgeleiteten Seeds pro Element und aggregierter Berichterstattung.

**Warum jetzt.** Die CLI verarbeitet ein Dokument pro Run; das Erzeugen eines
Trainingskorpus durch manuelle Aufrufschleifen verliert Seed-Disziplin (Gefahr
korrelierter Seeds, Determinismus-Audit N4) und Provenienz. Skalierbarkeit ist
ein zentrales Pipeline-Ziel (PLAN.md FF2/FF3).

**Ergebnisse.** `docs/architecture/batch-mode-spec.md`: Eingabemanifestformat,
Seed-Ableitung pro Element über `derive_seed` (WP-G), Ausgabelayout (ein
Run-Verzeichnis pro Element plus Batch-Manifest), Semantik der
Fehlerisolierung, Fortsetzungsverhalten und CLI-Oberfläche
(`injection-pipeline batch ...`).

**Abhängigkeiten.** WP-G implementiert (`derive_seed`, injizierbare Uhr), WP-D
abgeschlossen (Stufenfunktionen ohne CLI aufrufbar). **Hebel.** Hoch für das
Forschungsziel, in der Reihenfolge später.

---

## WP-N — Docstring- und Kommentar-Migration (mechanische Implementierung)

**Ziel.** Die widersprüchlichen Dokumentationskonventionen abgleichen und
anschließend Produktionsfunktionen in das ausgewählte Format migrieren.

**Warum jetzt.** `AGENTS.md` verlangt Google-Style-Docstrings, während das
aktive `commenting-guidelines`-Skill `# Input:/# Output:`-Blöcke verlangt. Der
Code folgt dem Skill bereits in vielen Modulen; eine mechanische Migration vor
der Wahl einer Quelle der Wahrheit würde den Konflikt wiederherstellen.

**Aufgaben.** Entscheiden, welche Konvention maßgeblich ist, `AGENTS.md` und das
Skill angleichen und anschließend die verbleibenden Funktionen in einem
separaten Durchlauf migrieren.

**Umfang / DoD.** Eine dokumentierte Konvention, keine gemischte Vorgabe,
ruff/mypy erfolgreich und keine Verhaltensänderungen. **Abhängigkeiten.**
Entscheidung zur Dokumentationskonvention. **Hebel.** Niedrig bis mittel
(Lesbarkeit, Konsistenz).

---

## WP-O — Deklarative CLI-Parameterspezifikation (kleines Design)

**Ziel.** Eine Parametertabelle, die sowohl argparse als auch den interaktiven
Modus steuert.

**Warum jetzt.** Der interaktive Modus implementiert jeden Standardwert und
Validator manuell neu (`cli.py:174-234` gegenüber `cli.py:255-319`); beide
Varianten müssen heute manuell synchron gehalten werden, und eine künftige
Run-Konfigurationsdatei wäre eine dritte Kopie.

**Ergebnisse.** Kurze Spezifikation in `docs/architecture/`, die den
Parameter-Deskriptor (Name, Typ, Standard, Auswahl, Validator, Prompt-Text,
Hilfe), die Erzeugung von argparse und Prompt-Schleife daraus sowie seinen Ort
in `config/` definiert. Die Migrationszuordnung für alle 11 aktuellen
Parameter aufnehmen.

**Abhängigkeiten.** WP-D, Schritt 1 (Optionsmodul). **Hebel.** Mittel — beseitigt
eine dauerhafte Synchronisationsgefahr, bevor der PDF-Subbefehl
(`compose-pdf`) weitere Parameter hinzufügt.

---

## WP-P — Wiederverwendung des Engine-Render-Passes (Implementierung, Performance)

**Ziel.** Nicht mehr jedes Overlay zweimal rendern.

**Implementiert am 2026-07-13.** Die Platzierung übergibt nun eine private
typisierte `PreparedOverlay`-Payload vom Größenbestimmungslauf an den finalen
Render-Lauf, sodass Font- und Handschrift-Overlays einmal pro Annotation
vorbereitet werden. Der Cache liegt nur auf intern positionierten Annotationen
und wird nicht in öffentliche Records, Schemas, Annotationen oder DCM/JPG-
Artefakte serialisiert. Fokussierte Tests zählen einen Vorbereitungslauf pro
Annotation für beide Renderertypen; der DICOM/JPG-E2E-Harness hält die
Artefakt-Hashes unverändert.

**Hinweis zum Microbenchmark.** Wiederverwenden von
`tests/unit/test_overlay_reuse.py::test_overlay_reuse_microbenchmark_fixture_is_reproducible`
als deterministisches Fixture für manuelle Zeitmessung, zum Beispiel dasselbe
feste `_inject_visible_text_into_frame`-Setup mit `python -m timeit` ausführen
und Mediane außerhalb von pytest vergleichen. Keine Zeitschwellenwerte zur CI
hinzufügen.

**Ursprüngliches Problem.** Die Platzierung renderte jedes Overlay einmal zur
Messung, und die Render-Stufe renderte es erneut. WP-P verwendet nun das
vorbereitete Overlay wieder; die Vermeidung doppelter Arbeit wird mit einem
Batch-Modus (WP-M) noch wichtiger.

**Aufgaben.** Das vorbereitete Overlay aus dem Größenbestimmungslauf (nach
Plan-Element verschlüsselt) cachen und in `_render_single_annotation`
wiederverwenden; der Byte-Identitäts-Harness weist unveränderte Ausgabe nach;
Microbenchmark vorher/nachher in der PR-Beschreibung dokumentieren.

**Umfang / DoD.** Für DCM/JPG erledigt: byteidentische Ausgaben, keine Änderung
der öffentlichen API und fokussierte Tests zur Wiederverwendung. Messbare
Beschleunigung sollte mit dem obigen deterministischen Fixture in einer
künftigen PR-/Release-Notiz festgehalten werden. **Abhängigkeiten.** WP-E-
Aufteilung abgeschlossen, WP-I-Harness. **Hebel.** Bis WP-M niedrig, danach
mittel.

---

## WP-Q — Provenienzaufteilung des Run-Manifests (kleines Design)

**Ziel.** `run_manifest.json` eigenständige, nur für Provenienz bestimmte Inhalte
geben, statt `ground_truth.json` zu duplizieren.

**Warum jetzt.** ADR-0004 dokumentiert die Duplizierung als beabsichtigt, aber
vorübergehend; WP-Bs `RunRecord` plus der `reproducibility`-Block aus WP-G
ermöglichen die natürliche Aufteilung (Annotationen → Ground Truth;
Parameter/Umgebung → Manifest).

**Ergebnisse.** Ersetzendes ADR für ADR-0004, das beide Dateiinhalte, die
Schema-Versionsanhebung (ADR-0008-Versionslinie) und Migrationshinweise für
Konsumenten definiert.

**Abhängigkeiten.** WP-B und WP-G implementiert. **Hebel.** Niedrig bis mittel
(Klarheit, kleinere Ground-Truth-Dateien).

---

## WP-R — Ausgabe- und CLI-Hygiene-Bundle (kleine Implementierung)

**Ziel.** Drei kleine Schwachstellen in überprüfbaren Durchläufen bereinigen.

**Aufgaben.**
1. **Transparenz der JPEG-Neukodierung.** Offen. JPG-Runs werden weiterhin mit
   Pillow-Standards neu kodiert. ADR-0008 hat kein Ausgabeversions-Gate für
   zusätzliche `render_metadata`-Felder, daher zeichnet dieser Durchlauf keine
   unvollständigen Encoder-Einstellungen auf. Konfigurierbare Qualität bleibt
   hinter einem späteren Bytekompatibilitäts-ADR.
2. **stdout-Rauschen von `identity_b`.** Erledigt am 2026-07-13. Die ungenutzte
   Generierung der zweiten Identität und ihre stdout-Ausgabe wurden entfernt.
   `derive_seed()` bleibt für echte benannte Zufallsstreams verfügbar.
3. **Hygiene des Preview-Writers.** Erledigt am 2026-07-13. Die interne
   `python -m injection_pipeline.writers.preview`-CLI bleibt nicht registriert,
   benötigt `--dicom`, hat keinen patientenähnlichen Standardpfad und öffnet ein
   Matplotlib-Fenster, wenn der Aufrufer `--show` übergibt.

**Umfang / DoD.** Dieser Durchlauf deckt Identitäts- und Preview-Hygiene mit
Tests ab; in `src/` verbleiben keine hardcodierten Patientenpfade unter
`DicomData/`. Verbleibende DoD: Das ADR-0008-Ausgabe-Gate entscheiden, bevor
JPEG-Encoder-Einstellungen zu `render_metadata` hinzugefügt werden.
**Abhängigkeiten.** WP-I-Harness; der verbleibende JPEG-Punkt hängt ebenfalls
von der ADR-0008-Versionsentscheidung ab. **Hebel.** Niedrig.

---

## Empfohlene Reihenfolge

```text
Architekturübergaben (docs/architecture/*, ADR-Review)   für DICOM/JPG-Kern erledigt
WP-I  E2E-Harness + CI                         erledigt 2026-07-12
WP-J  ScrabbleGAN + Injektionsintegration      implementiert; ADR-0010 und vollständige Gates offen
      nach den DICOM/JPG-Übergaben WP-B..WP-G:
WP-K  Validatoren und DICOM-Konformität
WP-L  Multi-Frame-Richtlinie                   offen, zusammen mit WP-K
WP-O  Deklarative Parameterspezifikation       offen, nach WP-D-Stufenaufteilung
WP-N  Docstring-Migration                      offen, im aktuellen Durchlauf nur Stichproben
WP-Q  Manifestaufteilung                       offen, nach ADR-0008-Versionsentscheidung
WP-M  Batch-Modus                              offen, nach WP-G-Seed-/Uhr-Kern
WP-P  Wiederverwendung des Render-Passes       erledigt 2026-07-13
WP-R  Hygiene-Bundle                           teilweise implementiert; JPEG-Punkt wartet auf ADR-0008
```

## Ausführung eines Pakets

Design-Pakete: Eine neue Fable-Sitzung auf ein Paket ansetzen („WP-K aus
`docs/fable-work-packages.md` ausführen; den referenzierten Code lesen, die
Dokumente als Ergebnis erzeugen, mit einer Implementierungsübergabe enden;
`src/` nicht ändern“). Implementierungspakete: Den Paketabschnitt samt
referenzierter Spezifikation direkt an Opus/Codex übergeben. Ein Paket pro
Sitzung bearbeiten.
