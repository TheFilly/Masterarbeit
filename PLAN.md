# Implementierungsplan InjectionPipeline

## Ziel

Dieser Plan priorisiert die Arbeit fuer die Masterarbeit entlang der drei Forschungsfragen:

- FF1: Formatunabhaengiges Daten- und Annotationsmodell
- FF2: Reproduzierbare, skalierbare Injektionspipeline
- FF3: Technische Verifikation und Qualitaetskriterien

Die Planung folgt der zentralen Abhaengigkeit des Projekts: Ohne belastbare Datenanalyse ist weder ein stabiles abstraktes Dokumentmodell noch eine sinnvolle Injektionslogik moeglich.

## Aktueller Stand aus dem Repo

Im Repo liegen bereits mehrere relevante Datenarten vor:

- Tabellarische MIMIC-Daten als `csv` und `csv.gz`
- Klinische Notizen mit Freitextfeldern in CSVs
- Freitextdateien als `txt`
- DICOM-Dateien als `dcm`
- Waveform/ECG-Dateien als `hea` und `dat`
- Bereits annotierte Beispielartefakte in `DycomData/Anonymization/...`

Die Codebasis ist strukturell vorbereitet, aber fachliche Modelle und Pipeline-Komponenten sind noch weitgehend offen. Der vorhandene Plan muss deshalb zuerst die fachliche Grundlage absichern.

## Priorisierung

1. Phase 1 komplettieren: Datenanalyse und Formatinventar
2. Daraus FF1 ableiten: abstraktes Dokument- und Annotationsmodell
3. Danach FF2 implementieren: Loader, Engine, Writer, Config, Identity Pool
4. Anschliessend FF3 absichern: Validierung, Reproduzierbarkeit, Qualitaetskriterien

## Agentenzuordnung

Im aktuellen Setup sind mehrere spezialisierte Agenten definiert:

- `Planner`: am besten fuer Planungsarbeit, Priorisierung, Risiken, Akzeptanzkriterien und Task-Zuschnitt
- `Data-Analyst`: am besten fuer Datensichtung, Formatinventar, Feld-/Schemaanalyse, PII-Traegeranalyse und MVP-Einschaetzungen auf Basis realer Dateien
- `Implementer`: am besten fuer klar abgegrenzte Umsetzungsaufgaben mit kleinen Diffs, Tests und technischer Ausfuehrung
- `Reviewer`: am besten fuer kritische Pruefung von Korrektheit, Reproduzierbarkeit, Typing, Architekturtreue und Testluecken

Empfohlene Arbeitsregel:

- Planungs- und Priorisierungsfragen primaer mit `Planner`
- Datenanalyse und Formatinventar primaer mit `Data-Analyst`
- Modellierungs- und Implementierungsarbeit primaer mit `Implementer`
- Vor Architekturentscheidungen, Schemafestlegungen und nach jedem groesseren Implementierungsblock ein gezieltes `Reviewer`-Review
- Bei riskanten Themen wie Taxonomie-Agnostik, Reproduzierbarkeit, DICOM-Validitaet und Ground-Truth-Konsistenz ist `Reviewer` Pflicht

## Phase 1 - Datenanalyse

### Ziel

Vollstaendiges Verstaendnis der im Repo vorhandenen Eingabeformate, potenziellen PII-Traeger und adressierbaren Einfuegestellen. Diese Phase ist Voraussetzung fuer alle folgenden Phasen.

### Agentenempfehlung

- Primaer: `Data-Analyst`
- Optional vorgelagert: `Planner` fuer Analyseumfang, MVP-Kriterien und Ergebnisstruktur
- Review-Gate: `Reviewer` fuer die Konsolidierung der Analyseergebnisse und die MVP-Formatentscheidung

### TODOs

- [ ] Vollstaendiges Formatinventar des Verzeichnisses `DycomData/` erstellen
- [ ] Formate in Eingangsdaten vs. abgeleitete/annotierte Referenzartefakte trennen
- [ ] Pro Datensatzfamilie festhalten, welche Dateien fuer die Pipeline echte Inputs sein sollen
- [ ] CSV-Dateien gruppieren nach Bereich:
  - `MIMIC-IV/hosp`
  - `MIMIC-IV/icu`
  - `MIMIC-IV-ED/ed`
  - `MIMIC-IV-Note/note`
  - `MIMIC-IV-ECG-subset`
  - `MIMIC-IV-Waveform-subset`
- [ ] Fuer jede relevante CSV Stichprobenanalyse durchfuehren:
  - Spaltennamen
  - Datentypen
  - Schluesselspalten
  - Freitextspalten
  - Offensichtliche PII-nahe Spalten
  - Felder mit indirekten Identifikatoren wie Datum, Provider, Standort, IDs
- [ ] CSVs in Klassen einteilen:
  - strukturierte Tabellen ohne Freitext
  - strukturierte Tabellen mit einzelnen textuellen Feldern
  - notizartige Tabellen mit grossen Freitextbloebcken
- [ ] Klinische Notizen in `discharge.csv`, `radiology.csv` und vorhandenen `.txt`-Dateien analysieren:
  - Abschnittsstruktur
  - Zeilenumbrueche
  - Platzhalter/Maskierungen
  - typische Positionen fuer Namen, Daten, Orte, IDs
- [ ] DICOM-Dateien analysieren:
  - relevante Standard-Tags mit moeglichem PHI/PII-Bezug
  - private Tags identifizieren
  - Textfelder vs. kodierte Felder unterscheiden
  - Dateinamen als moegliche PII-Traeger bewerten
  - unterscheiden, ob CXR und Echo unterschiedliche DICOM-Profile brauchen
- [ ] `hea/dat`-Dateien analysieren:
  - welche Headerzeilen Metadaten enthalten
  - ob Subjekt-IDs, Zeitstempel oder Freitext im Header vorkommen
  - ob `dat`-Binaerdaten fuer die erste Version ueberhaupt veraendert werden muessen oder nur Header/Sidecar relevant sind
- [ ] PDF-Artefakte aus den ECG-Annotationen nur als Referenz klassifizieren:
  - pruefen, ob sie Pipeline-Input sein sollen oder nur Ergebnis-/Vergleichsartefakte sind
- [ ] Vorhandene Annotationen in `DycomData/Anonymization/deanonymized_with_labels/` als Goldstandard fuer Analyse nutzen:
  - welche Formate sind bereits annotiert
  - wie wurden Positionen bisher referenziert
  - welche PII-Arten tauchen praktisch auf
- [ ] Eine strukturierte Uebersicht der Erkenntnisse erstellen:
  - Format
  - Beispielpfade
  - potentielle PII-Traeger
  - adressierbare Einheiten
  - technische Risiken fuer Injection/Rewrite

### Task-zu-Agent-Mapping

- Analyseauftrag strukturieren, Analysefragen priorisieren, Outputformat der Formatmatrix festlegen: `Planner`
- Formatinventar, CSV-Stichproben, Notizstruktur, DICOM-/HEA-Sichtung: `Data-Analyst`
- Konsolidierung der Formatmatrix und technische Risikoanalyse: `Data-Analyst`
- Plausibilisierung der MVP-Auswahl und Pruefung, ob relevante Formatklassen uebersehen wurden: `Reviewer`
- Pruefung, ob PII-Traeger sauber von externem Identifier-Schema getrennt gedacht werden: `Reviewer`

### Erwartete Outputs

- Ein Dateninventar mit allen fuer die Pipeline relevanten Dateitypen
- Eine Formatmatrix mit:
  - Format
  - Speicherform
  - logische Dokumenteinheit
  - adressierbare Stelle
  - moegliche PII-Traeger
  - erwartete Schreibstrategie
- Eine priorisierte Liste der Formate fuer die Erstimplementierung
- Eine Entscheidung, welche Formate in MVP v1 unterstuetzt werden und welche spaeter folgen
- Eine Liste technischer Risiken je Format

### Abhaengigkeiten

- Keine fachlichen Abhaengigkeiten, Startphase
- Fuer DICOM-Analyse ist Zugriff auf Beispiel-Dateien im Repo ausreichend
- Fuer spaetere Modellierung muss diese Phase abgeschlossen oder zumindest fuer MVP-Formate stabil sein

### Definition of Done

- Alle im Repo vorhandenen Eingabeformate sind katalogisiert
- Fuer jedes relevante Format sind PII-Traeger und adressierbare Stellen dokumentiert
- Es ist klar, welche Formate in Phase 2 und 3 zuerst modelliert werden

## Phase 2 - Abstraktes Dokumentmodell (FF1)

### Ziel

Ein formatunabhaengiges Pydantic-Modell definieren, das die in Phase 1 identifizierten Dokumenttypen und Zielstellen einheitlich abbildet.

### Agentenempfehlung

- Optional vorgelagert: `Planner` fuer Scope und Modellentscheidungen mit grosser Tragweite
- Primaer: `Implementer`
- Review-Gate: `Reviewer` vor Finalisierung von Modellen, JSONL-Schema und Adressierungslogik

### TODOs

- [ ] Auf Basis von Phase 1 die kleinste gemeinsame Abstraktion fuer "Dokument" definieren
- [ ] Dokumentarten festlegen, z. B.:
  - tabellarische Zeile/Zelle
  - Freitextdokument
  - DICOM-Datensatz
  - Waveform/ECG-Headerdokument
- [ ] Einheitliches Adressierungsmodell entwerfen fuer:
  - Feldreferenzen bei Tabellen
  - Textspannen in Freitext
  - Tagreferenzen in DICOM
  - Headerzeilen/Felder in `hea`
- [ ] Trennung zwischen Quelldokument, adressierbarer Stelle und Injektionsoperation modellieren
- [ ] Pydantic-Modelle fuer Kernobjekte definieren:
  - `Document`
  - `DocumentLocation`
  - `DocumentFragment` oder aequivalente adressierbare Einheit
  - `InjectionAnnotation`
  - `IdentityReference`
  - `GroundTruthRecord`
- [ ] Festlegen, wie Insert vs. Replace im Modell beschrieben wird
- [ ] Festlegen, wie Offsets gespeichert werden:
  - bytebasiert
  - zeichenbasiert
  - zeilen-/spaltenbasiert
  - formatabhaengig mit gemeinsamer Oberflaeche
- [ ] Definieren, wie Identitaetszuordnung gespeichert wird, ohne PII-Typen zu hardcoden
- [ ] Ground-Truth-Format als JSONL spezifizieren:
  - Dokument-ID
  - Positionsreferenz
  - Identifier-Typ aus externem Schema
  - synthetischer Wert
  - Identity-ID
  - Operation
  - Metadaten fuer Reproduzierbarkeit
- [ ] Beispiele fuer jedes Format erstellen, um das Modell gegen reale Daten zu pruefen
- [ ] Modellreview gegen Forschungsfrage FF1 durchfuehren:
  - generalisierbar
  - formatunabhaengig
  - dennoch praezise adressierbar

### Task-zu-Agent-Mapping

- Entwurf der Pydantic-Modelle und Beispielinstanzen: `Implementer`
- Ausarbeitung der einheitlichen Positionsadressierung: `Implementer`
- Review der Architekturprinzipien:
  - keine hartkodierten PII-Kategorien
  - saubere Trennung von Dokument, Annotation und Identitaet
  - ausreichende Praezision fuer Text, Tabellen, DICOM und `hea`
  Diese Pruefung: `Reviewer`
- Review des Ground-Truth-JSONL-Formats auf Stabilitaet und spaetere Validierbarkeit: `Reviewer`

### Erwartete Outputs

- Pydantic-Schemas fuer Dokument, Zielstellen und Annotationen
- Ein schriftlich festgehaltenes Adressierungsmodell
- JSONL-Spezifikation fuer Ground Truth
- Beispielinstanzen fuer CSV, Freitext, DICOM und `hea`

### Abhaengigkeiten

- Benoetigt die Ergebnisse aus Phase 1
- Sollte vor Implementierung von Loadern, Engine und Writer stabilisiert werden

### Definition of Done

- Fuer alle MVP-Formate kann dieselbe Dokumentabstraktion verwendet werden
- Jede Injektionsstelle ist einheitlich referenzierbar
- Ground Truth ist unabhaengig vom nativen Dateiformat speicherbar

## Phase 3 - Pipeline-Kern (FF2)

### Ziel

Die eigentliche Injektionspipeline implementieren: native Formate einlesen, in das abstrakte Modell ueberfuehren, synthetische Werte injizieren und wieder formatkonform ausschreiben.

### Agentenempfehlung

- Optional vorgelagert: `Planner` fuer MVP-Reihenfolge und Schnittgrenzen zwischen Komponenten
- Primaer: `Implementer`
- Review-Gates: `Reviewer` nach jedem groesseren Teilblock, insbesondere Engine, Config, Identity Pool und DICOM-Writer

### TODOs

#### 3.1 Loader-Adapter

- [ ] Priorisierte Loader-Reihenfolge fuer MVP festlegen, empfohlen:
  - CSV mit strukturierten Feldern
  - Notiz-CSV mit Freitext
  - `.txt`
  - DICOM
  - `hea`
- [ ] Pro Format einen Loader entwerfen, der native Daten in das abstrakte Dokumentmodell mappt
- [ ] Einheitliche Loader-Schnittstelle definieren
- [ ] Dokument-IDs und stabile Referenzen je Loader erzeugen
- [ ] Fehlerbehandlung fuer unvollstaendige oder unerwartete Dateien definieren

Empfohlener Agent:

- Implementierung der Loader: `Implementer`
- Review auf korrekte Modellabbildung und stabile Referenzen: `Reviewer`

#### 3.2 Injection Engine

- [ ] Operationen `insert` und `replace` als Engine-Kern implementieren
- [ ] Reihenfolge mehrerer Injektionen in einem Dokument deterministisch machen
- [ ] Konfliktregeln definieren:
  - ueberlappende Spannen
  - mehrere Ersetzungen im selben Feld
  - feldbasierte vs. textspannungsbasierte Eingriffe
- [ ] Engine so gestalten, dass sie taxonomie-agnostisch bleibt
- [ ] Ground-Truth-Records waehrend der Injektion erzeugen
- [ ] Seed-gesteuerte Zufallslogik zentral kapseln

Empfohlener Agent:

- Implementierung der Engine und deterministischen Injektionslogik: `Implementer`
- Review auf Korrektheit, Reproduzierbarkeit, Konfliktbehandlung und Taxonomie-Agnostik: `Reviewer`

#### 3.3 Writer-Adapter

- [ ] Writer pro MVP-Format implementieren
- [ ] Sicherstellen, dass nur die vorgesehenen Stellen geaendert werden
- [ ] Dateinamenstrategie definieren:
  - Original erhalten
  - neue Datei erzeugen
  - Sidecar fuer Ground Truth
- [ ] Formatgueltigkeit nach dem Schreiben sicherstellen, besonders fuer DICOM

Empfohlener Agent:

- Implementierung der Writer: `Implementer`
- Review auf unbeabsichtigte Seiteneffekte, Formatvaliditaet und Risiko bei DICOM-Rewrites: `Reviewer`

#### 3.4 Config-Schema

- [ ] Pydantic-Config fuer einen Pipeline-Run entwerfen
- [ ] Konfigurierbar machen:
  - Input-Pfade
  - Output-Pfade
  - aktivierte Formate
  - Seed
  - Anzahl/Strategie der Injektionen
  - Mapping zum externen `IdentifierSchema`
  - Auswahl der Writer/Validatoren
- [ ] MVP-Default-Config definieren

Empfohlener Agent:

- Entwurf und Implementierung des Config-Schemas: `Implementer`
- Review auf API-/Schema-Stabilitaet und Reproduzierbarkeitsanforderungen: `Reviewer`

#### 3.5 Identity Pool

- [ ] Schnittstelle zum externen `IdentifierSchema` finalisieren
- [ ] Identity-Pool-Modell definieren:
  - Identity-ID
  - Wertecontainer
  - deterministische Generierung
- [ ] Faker-basierte Generatoren kapseln
- [ ] Regeln fuer konsistente Mehrfachverwendung derselben synthetischen Identitaet definieren
- [ ] Missing-value-Strategie definieren, wenn fuer einen Identifier kein Generator vorhanden ist

Empfohlener Agent:

- Implementierung des Identity Pools und der Generator-Schnittstellen: `Implementer`
- Review auf Taxonomie-Agnostik, deterministische Generierung und korrekte Trennung von Identifier-Typ und Generatorlogik: `Reviewer`

#### 3.6 Tests

- [ ] Unit-Tests fuer alle oeffentlichen Loader/Writer/Engine-Komponenten
- [ ] Integrationstests mit kleinen echten Repo-Samples je MVP-Format
- [ ] Snapshot- oder Golden-File-Tests fuer Ground-Truth-JSONL einrichten

Empfohlener Agent:

- Testimplementierung: `Implementer`
- Testlueckenanalyse und Risikopruefung: `Reviewer`

### Erwartete Outputs

- Funktionsfaehige MVP-Pipeline fuer priorisierte Formate
- Konfigurierbarer Pipeline-Run mit Seed
- Ground-Truth-Ausgabe als JSONL
- Testabdeckung fuer Kernkomponenten

### Abhaengigkeiten

- Benoetigt das Modell aus Phase 2
- Benoetigt klare MVP-Formatentscheidung aus Phase 1
- Writer koennen erst sauber finalisiert werden, wenn Engine-Verhalten stabil ist

### Definition of Done

- Mindestens ein kompletter End-to-End-Run funktioniert fuer die priorisierten MVP-Formate
- Dieselbe Konfiguration plus derselbe Seed erzeugen denselben Output
- Output-Dokumente und Ground Truth sind gemeinsam reproduzierbar erzeugbar

## Phase 4 - Validierung (FF3)

### Ziel

Technisch nachweisen, dass die Injektionen korrekt, formatgueltig und reproduzierbar sind.

### Agentenempfehlung

- Optional vorgelagert: `Planner` fuer Qualitaetskriterien und Abnahmestrategie
- Primaer: `Implementer`
- Review-Gate: `Reviewer` fuer die Bewertung, ob die Validierung wirklich die Forschungsfrage FF3 abdeckt

### TODOs

#### 4.1 Positionskonsistenz

- [ ] Validator bauen, der prueft, ob Ground-Truth-Positionen mit dem geschriebenen Output uebereinstimmen
- [ ] Fuer Textspannen pruefen:
  - Start/Ende korrekt
  - injizierter Wert exakt vorhanden
- [ ] Fuer Feldersetzungen pruefen:
  - Ziel feldgenau geaendert
  - keine unbeabsichtigten Nebenwirkungen
- [ ] Fuer DICOM/`hea` pruefen:
  - referenzierte Tags/Headerfelder korrekt aktualisiert

Empfohlener Agent:

- Implementierung der Validatoren: `Implementer`
- Review auf Vollstaendigkeit der Konsistenzpruefungen: `Reviewer`

#### 4.2 Formatvaliditaet

- [ ] CSV/TXT-Outputs gegen parsbare Struktur pruefen
- [ ] DICOM-Outputs mit `pydicom` validieren
- [ ] `hea`-Outputs gegen WFDB-kompatible Struktur pruefen
- [ ] Fehlerfaelle definieren und automatisiert testen

Empfohlener Agent:

- Implementierung der Formatvalidatoren: `Implementer`
- Review auf false negatives/false positives und DICOM-Risiken: `Reviewer`

#### 4.3 Reproduzierbarkeit

- [ ] Tests implementieren, die identische Runs bei gleichem Seed vergleichen
- [ ] Tests implementieren, die unterschiedliche Seeds auch unterschiedliche Ergebnisse liefern lassen
- [ ] Determinismusgrenzen dokumentieren, z. B. Reihenfolge von Dateien oder Serialisierung

Empfohlener Agent:

- Implementierung der Reproduzierbarkeitstests: `Implementer`
- Review auf verdeckte Nicht-Determinismen und unklare Seed-Semantik: `Reviewer`

#### 4.4 Qualitaetskriterien

- [ ] Messbare technische Kriterien definieren:
  - Formatgueltigkeit
  - Positionskonsistenz
  - Vollstaendigkeit der Ground Truth
  - Reproduzierbarkeit
  - Fehlertoleranz bei nicht unterstuetzten Feldern
- [ ] Kriterien in automatisierte Testfaelle uebersetzen
- [ ] Ergebnisse fuer die Thesis dokumentierbar machen

Empfohlener Agent:

- Ableitung und technische Uebersetzung der Kriterien: `Implementer`
- Kritische Bewertung, ob die Kriterien die FF3 ausreichend operationalisieren: `Reviewer`

### Erwartete Outputs

- Validierungsmodul fuer Positionskonsistenz und Formatgueltigkeit
- Automatisierte Reproduzierbarkeitstests
- Explizite technische Qualitaetskriterien fuer FF3
- Nachvollziehbare Ergebnisbasis fuer die Masterarbeit

### Abhaengigkeiten

- Benoetigt lauffaehige Pipeline-Komponenten aus Phase 3
- Teilweise rueckgekoppelt zu Phase 2, falls Positionsmodell sich als unzureichend erweist

### Definition of Done

- Korrektheit der Annotationen ist automatisiert pruefbar
- Formatgueltigkeit ist fuer MVP-Formate automatisiert abgesichert
- Reproduzierbarkeit ist testbar und nachgewiesen

## Empfohlene Umsetzungsreihenfolge innerhalb des MVP

1. Phase 1 komplett fuer alle im Repo sichtbaren Formate
2. MVP-Entscheidung treffen: zuerst CSV + Notiz-CSV + TXT
3. Dokumentmodell fuer diese MVP-Formate finalisieren
4. End-to-End-Pipeline fuer CSV/Text bauen
5. Ground Truth und Reproduzierbarkeit absichern
6. Danach DICOM integrieren
7. Danach `hea/dat` bzw. ECG/Waveform-Header integrieren
8. Validierungsmodul ausbauen und thesis-faehige Qualitaetskriterien festziehen

Empfohlene Agentenabfolge:

1. `Planner` schneidet Phase 1 in konkrete Analysepakete und Entscheidungspunkte
2. `Data-Analyst` bearbeitet Phase 1 und erstellt die Formatmatrix
3. `Reviewer` prueft Analysequalitaet und MVP-Zuschnitt
4. `Planner` verdichtet die Analyse in Modellierungsentscheidungen fuer FF1
5. `Implementer` entwirft Phase-2-Modelle
6. `Reviewer` prueft Modell, JSONL und Taxonomie-Agnostik
7. `Implementer` setzt Pipeline-Kern iterativ um
8. `Reviewer` prueft nach jedem groesseren Block:
   - Loader
   - Engine
   - Writer
   - Config/Identity
9. `Implementer` baut Validatoren und Reproduzierbarkeitstests
10. `Reviewer` macht Abschlussreview mit Fokus auf FF2/FF3-Risiken

## Offene Entscheidungen, die frueh geklaert werden sollten

- Welche Formate gehoeren zum MVP der Masterarbeit und welche nur in den Ausblick?
- Sind PDFs echte Zielartefakte oder nur abgeleitete Referenzen?
- Sollen bei DICOM nur Metadaten injiziert werden oder auch eingebrannter Bildtext betrachtet werden?
- Sollen `dat`-Binaerdaten unangetastet bleiben und nur `hea`/Metadaten veraendert werden?
- Wie eng soll sich die erste Version an die bereits vorhandenen Annotationen in `DycomData/Anonymization/` anlehnen?

## Konkrete naechste Schritte

- [ ] Phase 1 starten mit einem systematischen Formatinventar aller Dateien unter `DycomData/`
- [ ] Analyse-Template fuer die Formatmatrix anlegen
- [ ] Relevante Beispiel-Dateien pro Format auswaehlen
- [ ] Fuer CSV, TXT, DICOM und `hea` jeweils erste PII-Traegerlisten erstellen
- [ ] Danach erst Modellierung aus Phase 2 beginnen

## Praktische Delegationsempfehlung

- Nutze `Planner`, wenn aus Forschungsfragen zuerst ein sinnvoller Arbeitsschnitt oder Meilensteinplan abgeleitet werden muss
- Gib `Data-Analyst` abgegrenzte Analyseaufgaben, z. B. "erstelle eine Formatmatrix fuer CSV/Note/DICOM", "analysiere DICOM-Tags", "identifiziere Freitextfelder und potenzielle PII-Traeger"
- Gib `Implementer` immer genau einen abgegrenzten Task, z. B. "implementiere CSV-Loader", "schreibe Reproduzierbarkeitstests fuer Engine"
- Nutze `Reviewer` nicht fuer Erstimplementierung, sondern fuer gezielte Reviews nach Meilensteinen
- Besonders review-pflichtig sind:
  - jede Schema- oder Modellentscheidung
  - jede Aenderung an Ground Truth
  - jede Reproduzierbarkeitslogik
  - jede DICOM-Schreiblogik
  - jede Stelle, an der versehentlich PII-Typen hardcodiert werden koennten
