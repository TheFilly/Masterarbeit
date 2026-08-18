# Handschrift-Tools

Dieses Verzeichnis enthält isolierte Tools für Handschrift-Assets, die vom
Injektions-Workflow verwendet werden.

Erzeugte Bilder, Masken, Manifeste, Checkpoints, Logs und Quellcode von
Drittanbietern
gehören unter `DicomData/HandwritingAssets/` oder einen anderen ignorierten
lokalen Pfad. Sie dürfen nicht versioniert werden.

Das ScrabbleGAN-Subtool besitzt nun den vom Host verwendeten Provider-/Cache-
Vertrag für `--font-family handwriting` und den eigenständigen Befehl
`uv run injection-pipeline generate-handwriting --seed <seed>`. Die Legacy-
Generator-Runtime bleibt weiterhin außerhalb der Python-3.13-Umgebung.

Der reale Docker-/Upstream-Checkpoint-Pfad wurde am 2026-07-15 lokal mit dem
offiziellen Amazon-Source-Checkout, dem englischen IAM-Options-Sidecar und dem
lokalen Checkpoint `latest_net_G.pth` verifiziert. Ein fehlender Checkpoint,
Options-Sidecar, `.git_commit`-/Git-Checkout-Metadatum oder eine fehlende
Generator-Runtime ist ein harter Fehler; es gibt keinen Fallback auf einen
normalen Font-Renderer.
