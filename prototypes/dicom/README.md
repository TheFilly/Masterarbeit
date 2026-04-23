# DICOM Injection Prototype

Quick-and-dirty Machbarkeitsnachweis: Synthetische PII in DICOM-Tags injizieren und einen Ground-Truth-Record erzeugen. Vorläufer der DICOM-Integration in Phase 3 der Pipeline.

## Zweck

- Verifizieren, dass pydicom relevante PII-Tags sicher lesen und schreiben kann
- Annotationsformat (JSONL Ground Truth) im Kleinen erproben
- Seed-gesteuerte Reproduzierbarkeit demonstrieren
- Wiederverwendbare Funktionen für die spätere Pipeline vorbereiten

## Ausführung

```bash
uv run python prototypes/dicom/inject.py
uv run python prototypes/dicom/inject.py --seed 99
uv run python prototypes/dicom/inject.py --seed 42 --output-dir prototypes/dicom/output/
```

## Eingabedatei

```
DycomData/Anonymization/original_data/patient_10080695_23273240/echo/91180014_0001.dcm
```

Echo-DICOM aus `original_data/` gewählt: enthält Placeholder-Werte in PII-Tags (z.B. `Male FirstName LastName` in PatientName), was den Injektionspunkt explizit macht. Reichere Metadaten-Struktur (Modalität US, GE-Gerät) gegenüber CXR.

## Ausgabe (`output/` — gitignored)

```
output/
├── echo_injected.dcm        # Modifizierte DICOM-Datei
└── ground_truth.jsonl       # Eine Zeile pro injiziertem Tag
```

## Injizierte DICOM-Tags

| Tag-Adresse | Keyword | VR | Beschreibung |
|---|---|---|---|
| `(0010,0010)` | PatientName | PN | Primärer Name-Träger |
| `(0010,0020)` | PatientID | LO | Patienten-ID |
| `(0010,0030)` | PatientBirthDate | DA | Geburtsdatum `YYYYMMDD` |
| `(0010,0040)` | PatientSex | CS | `M` oder `F` |
| `(0008,0050)` | AccessionNumber | SH | Accession-Nummer |

Nicht angefasst: PixelData, UIDs (StudyInstanceUID, SeriesInstanceUID), File Meta Information.

## Annotationsformat (ground_truth.jsonl)

Eine Zeile pro injiziertem Tag:

```json
{
  "schema_version": "0.1.0-prototype",
  "run_id": "proto-20260422-001",
  "seed": 42,
  "source_file": "DycomData/Anonymization/original_data/patient_10080695_23273240/echo/91180014_0001.dcm",
  "output_file": "prototypes/dicom/output/echo_injected.dcm",
  "injection": {
    "tag_address": "0010,0010",
    "tag_keyword": "PatientName",
    "dicom_vr": "PN",
    "injected_value": "Smith^John",
    "identity_field": "patient_name",
    "identity_id": "SYNTH-001"
  }
}
```

## Dateistruktur

```
prototypes/dicom/
├── README.md          # Dieser Plan
├── inject.py          # Orchestrierung (Quick and Dirty — wird weggeworfen)
├── identity.py        # Faker-Wrapper (wiederverwendbar → src/identity/)
├── dicom_writer.py    # pydicom-Interaktion (wiederverwendbar → src/writers/)
└── output/            # Gitignored
```

## Wiederverwendbarkeit

| Datei | Status | Ziel in Pipeline |
|---|---|---|
| `identity.py` | Direkt übernehmen | `src/injection_pipeline/identity/synthetic.py` |
| `dicom_writer.py` | Mit kleinen Anpassungen | `src/injection_pipeline/writers/dicom_writer.py` |
| `inject.py` | Wegwerfen | Ersetzt durch PipelineRunner + CLI |

## Seed-Strategie

- `--seed`-Argument, Default `42`
- Zwei Identitäten: `seed` und `seed + 1`
- `fake.seed_instance(seed)` pro Identität — kein globales `random.seed()`

## Nicht im Scope dieses Prototypen

- Kein Pydantic-Modell (direkte `dict`-Verwendung)
- Keine Fehlerbehandlung / Retry-Logik
- Kein structured Logging
- Keine Chunking-Strategie
- Kein Config-Schema
- DICOM-Tag-Exploration (VR-Verifikation) als separater Schritt vor Implementierung empfohlen
