# Audit zu Reproduzierbarkeit und Determinismus (WP-G)

Status: Seed- und Uhrzeitanpassungen am 2026-07-12 abgeschlossen;
Umgebungs-Provenienz bleibt hinter ADR-0008 offen. Dieses Audit ist die Basis
für ADR-0009 und umfasst Zufallsquellen, Uhren und Umgebungsabhängigkeiten in
`src/injection_pipeline/`.

Bewertungen: **violation** verletzt das Prinzip, **intended** ist
dokumentiertes Prototype-Verhalten, **honoured** ist seed-basiert oder
deterministisch, **environment** ist eine Reproduzierbarkeitseingabe außerhalb
der Zufallsentscheidungen.

## Inventar

| # | Quelle | Ort | Bewertung | Maßnahme / Status |
|---|---|---|---|---|
| N1 | Default-Input-Auswahl | `inputs.py` | **honoured** | In WP-G behoben. `select_seeded_default_input()` sortiert die Kandidaten und zieht mit `random.Random(derive_seed(seed, "input_selection"))`. |
| N2 | Zeitstempel aus der Wanduhr in `run_id` | `runner.py`, `cli.py` | **honoured** | In WP-G behoben. `run(args, now=...)` akzeptiert eine injizierte Uhr; die CLI stellt `--run-timestamp` als ISO-8601 bereit. |
| N3 | Faker-Identitätsgenerierung | `identity/generator.py` | **honoured** | Die direkte Semantik von `Faker.seed_instance(seed)` für `identity_a` bleibt erhalten; die Feldreihenfolge ist maßgeblich. Faker-Paket und Locale-Daten gehören weiterhin in eine künftige Umgebungsprovenienz. Siehe N14 für eine plattformspezifische Ausnahme im DOB-Rezept. |
| N4 | Ungenutzte zweite Identität | `runner.py` | **removed** | WP-R entfernte am 2026-07-13 die Generierung von `identity_b` und deren ausschließliche stdout-Ausgabe. |
| N5 | Platzierungs-RNG | `engine/pixel_injection.py`, `engine/injector.py` | **honoured** | Durch ADR-0009 als `"placement/raw-seed"` übernommen. Eine Migration zu `derive_seed()` würde Pixel verschieben und benötigt ein künftiges Byte-Kompatibilitäts-ADR. |
| N6 | Reihenfolge der Verzeichnisiteration | `inputs.py` | **honoured** | Sowohl die Kandidatensammlung als auch die geseedete Auswahl sortieren nach der kleingeschriebenen Pfadzeichenfolge. |
| N7 | Schriftdateien | `engine/fonts.py`, Pixel-Rendering | **environment** | Schriftpfad und Datei-Hash benötigen weiterhin RunRecord-Provenienz, sobald ADR-0008 eine kompatible ausgegebene Version ermöglicht. Die Kandidatenliste `_FONT_PATHS["arial"]` hängt davon ab, dass die Systemschriften auf dem Runner vorhanden sind; am 2026-07-14 wurde `/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf` (ohne „2“) ergänzt, weil Ubuntus `fonts-liberation2`-apt-Paket ein Übergangs-Platzhalter ist, der Liberation v1 am alten Pfad installiert (Debians `fonts-liberation2` installiert tatsächlich nach `liberation2/`; deshalb bestand zuvor ein Debian-basierter Container lokal, bevor der echte `ubuntu-latest`-Run das Problem aufdeckte). Die CI installiert `fonts-liberation2` nun ebenfalls per apt, bevor Tests ausgeführt werden, da einige Unit-Tests `arial` ohne festgelegte Fixture-Schrift auflösen. |
| N8 | Pillow-Rendering und Resampling | Pixel-Rendering und JPG-Kodierung | **honoured** (Layout-Engine); **environment** (Rest) | `load_default_font()` setzt als defensive Korrektur `layout_engine=ImageFont.Layout.BASIC` fest (2026-07-14): Pillow wählt sonst automatisch `RAQM`-Shaping, wenn das installierte Wheel `libraqm` enthält; das ist eine Eigenschaft des Plattform-Wheels, nicht der Pillow-Version. Ein Windows-Linux-A/B-Vergleich (Docker) am 2026-07-14 bestätigte, dass gerenderte `box_annotations`/Maskengrenzen und die Bytes von `synthetic_injected.{dcm,jpg}` mit dieser Festlegung bereits plattformübergreifend byteidentisch sind; N14 und nicht das Glyphen-Shaping verursachte den E2E-Record-Hash-Bruch. Die verbleibende Provenienz von Resampling und Versionen wartet weiterhin auf ADR-0008. |
| N9 | matplotlib-Previews | `writers/preview.py` | **environment** | Die gerenderten Pixel sind unter Windows/Linux byteidentisch (2026-07-14, Pixeldifferenz = 0), die PNG-Containerbytes jedoch nicht: Plattformspezifische Pillow-/matplotlib-Agg-Builds kodieren identische Pixel mit unterschiedlichen komprimierten Bytes neu. E2E-Binärreferenz-Hashes für `preview.png`/`preview_annotated.png` sind deshalb auf die CI-Kodierung (`ubuntu-latest`) festgelegt. Die Bibliotheksversions-Provenienz wartet weiterhin auf ADR-0008. |
| N10 | Bibliotheksversionen als Eingaben | Run-Umgebung | **environment** | Noch offen. ADR-0008 hat keine konfliktfreie ausgegebene RunRecord-Version für zusätzliche `reproducibility`-Felder. |
| N11 | numpy-Zufälligkeit | `src/` | **honoured** | Das Paket verwendet kein `np.random`. |
| N12 | pydicom-Schreibpfad | `writers/dicom.py` | **honoured** | Bei festem Input und pydicom deterministisch. Die Wiederverwendung von SOPInstanceUID bleibt außerhalb des Determinismusumfangs. |
| N13 | Interaktive Eingabeaufforderungen | `cli.py` | **intended** | Menschliche Entscheidungen landen in `args`; der interaktive Modus akzeptiert nun ebenfalls optional `run-timestamp`. |
| N14 | Faker-Kalendertag von `date_of_birth()` | `identity/recipes.py` | **honoured** | Das Identifier-Schema enthält `generator.reference_date = "2026-07-10"` sowie `reference_date_policy`; die DOB-Generierung liest das Systemdatum nicht mehr. Erneut am 2026-07-14 behoben: Das Rezept rief `fake.date_time_ad()` auf, dessen `_rand_seconds`-Hilfsfunktion (`faker/providers/date_time/__init__.py`) selbst nach `platform.system()` verzweigt — `randint` (Integer-Sekunden) unter Windows, `uniform` (Float-Sekunden) sonst — und dadurch den geseedeten RNG-Stream je Betriebssystem unterschiedlich verbrauchte. Das erzeugte bei gleichem Seed ein anderes Geburtsdatum. Dies war die tatsächliche Ursache des Windows-Linux-E2E-Record-Hash-Unterschieds; alle anderen Identitätsfelder und Box-Geometrien waren bereits plattformstabil. Das Rezept verwendet nun direkt `fake.random.randint()` statt `fake.date_time_ad()` und entspricht damit auf jeder Plattform dem früheren, nur unter Windows verwendeten Verhalten von Faker. Die von `identity_id` unabhängige Unit-Abdeckung (`test_date_of_birth_matches_reference_day_faker_path_and_ignores_execution_day`) prüft nun dieselben plattformunabhängigen Primitive statt `fake.date_of_birth()` gegen, das weiterhin den Betriebssystem-Zweig enthält und nicht mehr als plattformübergreifende Referenz dienen kann. |

`derive_seed(seed, name)` sind die ersten acht Bytes von
`sha256(f"{seed}:{name}".encode("utf-8"))` als Big-Endian-Ganzzahl. Pythons
eingebaute Funktion `hash()` darf nicht zur Seed-Ableitung verwendet werden.

## Reproduzierbarkeitsvertrag

Für eine feste Code-Version, Lockdatei der Abhängigkeiten, Schriftdateien und
ein Eingabedokument ist ein Injektions-Run eine reine Funktion von `(seed,
input, rotation, placement_mode, font_size_pct, font_family, text_background,
identifier_schema, run_timestamp)`. Injizierte Werte, gerenderte Pixel,
Annotationsgeometrie und Ground-Truth-Artefakte sind bei wiederholten Runs
byteidentisch.

Jede neue Zufallsentscheidung verwendet einen benannten Stream, der aus dem
Run-Seed und einem Stufennamen abgeleitet wird. `identity_a` behält das direkte
Faker-Seeding, und die Platzierung behält für Bytekompatibilität den
übernommenen Raw-Seed-Stream. Die Autoauswahl eines Default-Inputs ist geseedet
und zeichnet den aufgelösten Pfad auf, sodass ein Run durch Übergabe dieses
Pfads wiederholt werden kann.

Künftige RunRecord-Versionen sollten Umgebungsinputs aufzeichnen, die Bytes
beeinflussen können: Bibliotheksversionen, Plattform, Schriftpfade und
Schriftdatei-Hashes.

## Aktuelles offenes Gate

Der `reproducibility`-Block und die Provenienz des Identifier-Schemas sind
zusätzliche RunRecord-Felder. ADR-0008 hat über `0.2.0-prototype` hinaus noch
keine konfliktfreie ausgegebene Version, daher gibt WP-G keine unvollständigen
oder versionswidrigen Felder aus.

## Aktualisierung der Referenzen

E2E übergibt nun einen festen Zeitstempel und vergleicht die vollständigen
Artefaktbytes einschließlich `ground_truth.json` und `run_manifest.json`.
Referenz-Hashänderungen beschränken sich auf die DOB- und Zeitstempelkorrektur:

- Die DCM-Ausgabe-Bytes änderten sich, weil `PatientBirthDate` nicht mehr mit
  dem Ausführungstag abweicht.
- Die JSON-Artefaktbytes änderten sich, weil `run_id` nun den festen E2E-
  Zeitstempel statt eines normalisierten Wanduhrwerts verwendet.
- Die Preview-Bildbytes blieben unverändert, weil DOB im Prototype-Schema nur
  als Tag verwendet wird.

Referenzaktualisierung 2026-07-14 (siehe N14): `patient_birth_date` änderte
sich unter Linux, weil Fakers eigener `_rand_seconds` nach `platform.system()`
verzweigt; das DOB-Rezept hängt nicht mehr von diesem Zweig ab, und die
DCM/JPG-Record-Hashes entsprechen wieder dem zuvor unter Windows berechneten
Wert, da nun beide Plattformen übereinstimmen. Die Referenz-Hashes von
`ground_truth.json`, `run_manifest.json`, `preview.png` und
`preview_annotated.png` wurden erneut auf die vom CI-Runner (`ubuntu-latest`)
erzeugten Bytes festgelegt: Die JSON-Dateien enthalten absichtlich
`os.linesep`, und die PNGs sind plattformübergreifend pixelidentisch, werden
aber von einem plattformspezifischen Pillow-/matplotlib-Build neu kodiert
(siehe N8, N9). Lokal über einen
`ghcr.io/astral-sh/uv:python3.13-bookworm`-Container verifiziert, der die
CI-Schritte für Linting, Typprüfung und Tests reproduziert.
