# Ground-Truth-Schema-Änderungsprotokoll

Dieses Änderungsprotokoll ist die von ADR-0008 geforderte einzige
Versionshistorie. Run-Records und PDF-Annotations-Sidecars haben verschiedene
`record_type`-Werte, teilen sich aber denselben Versionsnamensraum.

## 0.3.0-pdf-prototype — 2026-07-14

PDF-Modalitäts-Sidecar hinzugefügt. Er verknüpft ein PDF-Eingabe-Template, ein
bereits injiziertes DICOM und das validierte DICOM-`ground_truth.json` mit der
erzeugten PDF-Datei und transformierten PDF-Raum-Annotations-Quads. PDF-
Eingabe/Ausgabe wird vom dedizierten PDF-Loader-/Writer-Paar verarbeitet;
Quelldateien werden nie verändert.

## 0.2.0-prototype — bestehend

Aktuelles DICOM/JPG-`RunRecord`-Schema. Bestehende Parser und
Byte-Kompatibilitäts-Fixtures bleiben gültig.

## Änderungsregeln

Zusätzliche Felder benötigen eine Minor-Version und ein Fixture. Breaking Reads
benötigen einen Major- (oder vor 1.0 Minor-)Versionssprung, einen
Migrationshinweis und ein ersetzendes ADR. Parser müssen weiterhin jede
veröffentlichte Version akzeptieren, sofern eine explizite Entscheidung sie
nicht außer Kraft setzt.
