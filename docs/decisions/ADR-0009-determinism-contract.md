---
id: ADR-0009
status: accepted
based_on:
  - docs/architecture/determinism-audit.md
---

# ADR-0009: Determinismusvertrag – benannte Seed-Streams, injizierbare Uhr und aufgezeichnete Umgebung

## Kontext

„Seed all randomness“ (`AGENTS.md`) hatte zwei dokumentierte Verletzungen: eine
Default-Input-Auswahl ohne Seed und eine `run_id` aus der Wanduhr. Identity B
verwendete `seed + 1`, wodurch die zweite Identität von `run(seed=42)` der
injizierten Identität von `run(seed=43)` entsprach. Faker
`date_of_birth()` verwendete außerdem den Ausführungstag als implizite Eingabe,
sodass ein fester Seed über Kalendertage hinweg abweichen konnte.

Das vollständige Inventar steht in `docs/architecture/determinism-audit.md`.

## Entscheidung

Der im Determinismus-Audit spezifizierte Reproduzierbarkeitsvertrag wird mit den
folgenden Kompatibilitätsausnahmen übernommen:

1. Jeder neue Zufallszugriff kommt aus einem **benannten Stream**, der über
   SHA-256 aus dem Run-Seed abgeleitet wird (zum Beispiel
   `derive_seed(seed, "input_selection")`). Der Code darf kein
   modulweites `random` verwenden.
2. **Uhren sind injizierbar.** `run()` akzeptiert einen Zeitstempel und die CLI
   stellt `--run-timestamp` als ISO-8601-Override bereit.
3. **Die Input-Auswahl ist deterministisch geseedet.** Die Auswahl des
   Default-Inputs verwendet den Stream `input_selection` über der sortierten
   Kandidatenliste. Der aufgelöste Input-Pfad wird weiterhin in `source_file`
   aufgezeichnet.
4. **Identity A behält das direkte Faker-Seeding.**
   `generate_identity(seed, schema)` verwendet für die injizierte Identität
   weiterhin `Faker.seed_instance(seed)`, damit die Identity-Bytes von WP-C
   stabil bleiben.
5. **Die Platzierung behält den unveränderten Seed.** Der Platzierungs-RNG ist
   der übernommene Stream `"placement/raw-seed"`. Eine Migration zu
   `derive_seed()` würde Pixel verschieben und benötigt ein künftiges
   Byte-Kompatibilitäts-ADR.
6. **Das Aufzeichnen der Umgebung wartet auf ADR-0008.** Der gewünschte
   `reproducibility`-Block und die Provenienz des Identifier-Schemas sind
   zusätzliche RunRecord-Felder, aber es gibt noch keine konfliktfreie
   ausgegebene RunRecord-Version. Die Implementierung darf sie nicht zu
   `0.2.0-prototype` hinzufügen.

Das Identifier-Schema legt zeitabhängige Faker-Semantik über
`generator.reference_date` und `generator.reference_date_policy` fest. Das
Prototype-Schema setzt `reference_date = "2026-07-10"`, um die Ausführungstags-
Eingabe von Faker-`date_of_birth()` zu entfernen. Seit dem 2026-07-14 verwendet
das Rezept die Convenience-Methoden `date_of_birth()`/`date_time_ad()` von Faker
überhaupt nicht mehr: Ihr internes `_rand_seconds` verzweigt nach
`platform.system()` (`randint` unter Windows, `uniform` sonst), was bei einem
festen Seed die Byte-Identität zwischen Betriebssystemen verletzt. Das Rezept
zieht den Offset des Altersfensters nun direkt über
`fake.random.randint()` und entspricht damit auf jeder Plattform dem früheren
nur unter Windows verwendeten Verhalten von Faker.

## Betrachtete Alternativen

- **Ein gemeinsamer RNG, der überall übergeben wird**: Die Reihenfolge der
  Entnahmen koppelt unabhängige Stufen. Ein zusätzlicher Zug in der
  Identitätsgenerierung würde die Platzierung ändern.
- **Globales `random.seed(seed)`**: Bibliothekscode, der den globalen Stream
  verwendet, bricht die Isolation unbemerkt.
- **Sofortiger Umgebungsblock im RunRecord**: Die Felder sind additiv, aber
  ADR-0008 verhindert weiterhin eine konfliktfreie ausgegebene Version.

## Konsequenzen

- Bei der Übernahme änderte die Seed-Ableitung `input_selection` und die nur auf
  stdout ausgegebene `identity_b`; WP-R entfernte die ungenutzte zweite
  Identität später vollständig.
- Die Platzierung bleibt bytekompatibel, weil ADR-0009 den unveränderten Seed
  ausdrücklich übernimmt.
- `identity_a` behält das direkte Faker-Seeding, während die DOB-Generierung
  nicht mehr das Systemdatum ausliest.
- Das Methodenkapitel der Arbeit kann den Vertrag in
  `docs/architecture/determinism-audit.md` zitieren.

## Implementierungsstatus

Am 2026-07-12 für Zufallszugriffe und Uhren implementiert:

- `seeding.derive_seed()` stellt Seeds für benannte Streams bereit.
- `inputs.select_seeded_default_input()` verwendet den Stream
  `input_selection` über sortierten Kandidaten.
- `runner.run(args, now=...)` akzeptiert einen injizierten Zeitstempel und die
  CLI stellt `--run-timestamp` bereit.
- Identifier-Schemas enthalten `reference_date` und `reference_date_policy`; das
  Standardschema setzt `2026-07-10` fest.

Die ungenutzte Generierung von `identity_b` wurde durch WP-R am 2026-07-13
entfernt. Die angenommene Regel, dass jeder künftige Zufallszugriff einen
benannten Stream verwendet, bleibt davon unberührt.

Am 2026-07-14 wurde `identity/recipes.py::date_of_birth` so geändert, dass die
Faker-Convenience-Methoden `date_of_birth()`/`date_time_ad()` nicht mehr
aufgerufen werden, weil deren interner Betriebssystem-Zweig die Byte-Identität
zwischen Windows und Linux bei gleichem Seed verletzte (siehe
`docs/architecture/determinism-audit.md` N14). Dieselbe Datumskorrektur machte
außerdem eine Lücke bei der Schrifterkennung in `ubuntu-latest`-CI sichtbar
(`docs/architecture/determinism-audit.md` N7/N8) sowie einen bereits vorher
bestehenden Plattformunterschied bei den rohen JSON/PNG-Artefaktbytes
(Zeilenenden, PNG-Neukodierung), der den Inhalt der geparsten Records nicht
beeinflusst; E2E-Binärreferenz-Hashes sind deshalb an die CI-(Linux)-Umgebung
gebunden.

Noch offen: Die Umgebungsprovenienz wird nicht ausgegeben, weil ADR-0008 noch
keine kompatible RunRecord-Version für zusätzliche Felder eröffnet hat.

## Review-Hinweise

Für WP-G auf Grundlage des WP-B/C/D/E-Paketzuschnitts angenommen. ADR-0008 ist
weiterhin die Voraussetzung für die Ausgabe der Felder `reproducibility` und
Identifier-Schema-Provenienz.
