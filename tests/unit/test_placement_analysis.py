"""Unit-Tests für die deskriptive Platzierungsanalyse."""

import json
from pathlib import Path

import pytest
from tools.thesis_results.placement_analysis.analysis import (
    _unbalanced_groups,
    analyze_paths,
    analyze_payloads,
    boxes_overlap,
    classify_corner,
    descriptive_statistics,
    extract_box_metrics,
    heatmap_parameters,
    image_dimensions,
    image_dimensions_with_source,
    summarize_run,
    write_analysis_outputs,
)
from tools.thesis_results.placement_analysis.collect_dataset import render_command


def _annotation(
    left: float, top: float, right: float, bottom: float
) -> dict[str, object]:
    return {
        "label": "A",
        "corners": [
            {"x": left, "y": top},
            {"x": right, "y": top},
            {"x": right, "y": bottom},
            {"x": left, "y": bottom},
        ],
    }


# Input: Keine; Output: Boxmetriken mit bekannten Geometriewerten.
# Prüft Normalisierung, Fläche, Seitenverhältnis, Randabstand und Metadaten.
def test_extract_box_metrics() -> None:
    payload = {
        "run_id": "r1",
        "seed": 7,
        "document_type": "jpg",
        "run_metadata": {"placement_mode": "free"},
        "render_metadata": {
            "rotation_degrees": 90,
            "font_family": "arial",
            "font_size_pct": 80,
        },
    }
    row = extract_box_metrics(
        Path("ground_truth.json"), payload, 200, 100, _annotation(10, 20, 50, 40), 2
    )
    assert row["normalized_width"] == pytest.approx(0.2)
    assert row["normalized_height"] == pytest.approx(0.2)
    assert row["normalized_area"] == pytest.approx(0.04)
    assert row["aspect_ratio"] == pytest.approx(2)
    assert row["center_x"] == pytest.approx(0.15)
    assert row["edge_distance"] == pytest.approx(0.05)
    assert row["corner_region"] == "none"
    assert row["annotation_index"] == 2
    assert row["rotation"] == 90


# Input: Corners-Annotation mit deklarierter Region.
# Output: Getrennte deklarierte Engine-Region und Mittelpunktregion.
# `corners` wird fachlich über `declared_region` nachgewiesen, nicht über den
# Mittelpunkt.
def test_declared_and_center_region_are_separate() -> None:
    payload = {"placement_mode": "corners"}
    annotation = _annotation(40, 40, 60, 60)
    annotation["region"] = "top_left"
    row = extract_box_metrics(Path("x"), payload, 100, 100, annotation, 0)
    assert row["declared_region"] == "top_left"
    assert row["center_region"] == "none"
    assert row["placement_mode"] == "corners"


# Input: Normalisierte Mittelpunkte; Output: Eckklassifikation.
# Deckt alle Eckbereiche und die neutrale Region ab.
def test_classify_corner() -> None:
    assert [
        classify_corner(*point)
        for point in ((0.1, 0.1), (0.9, 0.1), (0.1, 0.9), (0.9, 0.9), (0.5, 0.5))
    ] == ["top_left", "top_right", "bottom_left", "bottom_right", "none"]


# Input: Zwei Boxen; Output: Überlappungsstatus.
# Kantenkontakt ist absichtlich keine Überlappung.
def test_boxes_overlap() -> None:
    assert boxes_overlap((0, 0, 10, 10), (5, 5, 15, 15))
    assert not boxes_overlap((0, 0, 10, 10), (10, 0, 20, 10))


# Input: Zwei Boxmetriken desselben Runs; Output: aggregierte Run-Zeile.
# Prüft Medianwerte, Eckanteile und Paarzählung.
def test_summarize_run() -> None:
    payload = {"run_id": "r", "placement_mode": "corners"}
    rows = [
        extract_box_metrics(Path("x"), payload, 100, 100, _annotation(0, 0, 10, 10), 0),
        extract_box_metrics(Path("x"), payload, 100, 100, _annotation(5, 5, 20, 20), 1),
    ]
    result = summarize_run(rows)
    assert result["box_count"] == 2
    assert result["overlap_pair_count"] == 1
    assert result["corner_share_top_left"] == 1


# Input: Ground-Truth-Pfad mit Vorschau; Output: deren Pixelabmessungen.
# Die Vorschau hat Vorrang vor CLI-Fallbacks.
def test_image_dimensions_prefers_preview(tmp_path: Path) -> None:
    from PIL import Image

    path = tmp_path / "ground_truth.json"
    path.write_text(json.dumps({"preview_file": "preview.png"}), encoding="utf-8")
    Image.new("RGB", (12, 8)).save(tmp_path / "preview.png")
    assert image_dimensions(path, {"preview_file": "preview.png"}, 99, 99) == (
        12.0,
        8.0,
    )


# Input: Ground-Truth-Pfad ohne Vorschau; Output: Dimensionen oder `None`.
# Prüft gemeinsamen Fallback und fehlende Dimensionen.
def test_image_dimensions_fallback_and_missing(tmp_path: Path) -> None:
    path = tmp_path / "ground_truth.json"
    assert image_dimensions(path, {}, 12, 8) == (12, 8)
    assert image_dimensions(path, {}, None, None) is None
    with pytest.raises(ValueError):
        image_dimensions(path, {}, 0, 8)


# Input: Vorschaupfade in drei Schreibweisen; Output: jeweils erkannte Maße.
# Absolute, Ground-Truth-relative und Repository-relative Angaben bleiben robust.
def test_image_dimensions_path_variants(tmp_path: Path) -> None:
    from PIL import Image

    root = tmp_path / "repo"
    ground_truth = root / "runs" / "r1" / "ground_truth.json"
    ground_truth.parent.mkdir(parents=True)
    relative = root / "assets" / "relative.png"
    relative.parent.mkdir()
    Image.new("RGB", (11, 7)).save(relative)
    absolute = root / "assets" / "absolute.png"
    Image.new("RGB", (13, 9)).save(absolute)
    assert image_dimensions(
        ground_truth, {"preview_file": "../../assets/relative.png"}, repo_root=root
    ) == (11.0, 7.0)
    assert image_dimensions(
        ground_truth, {"preview_file": str(absolute)}, repo_root=root
    ) == (13.0, 9.0)
    assert image_dimensions(
        ground_truth, {"preview_file": "assets/relative.png"}, repo_root=root
    ) == (11.0, 7.0)


# Input: Eine Box außerhalb des Bildes; Output: Clipping- und Boundsstatus.
# Der Status bleibt in der Boxzeile und den bestehenden Validierungsfeldern sichtbar.
def test_extract_box_metrics_clipping() -> None:
    row = extract_box_metrics(
        Path("ground_truth.json"), {}, 100, 100, _annotation(-5, 5, 20, 20), 0
    )
    assert row["within_bounds"] is False
    assert row["text_not_clipped"] is False
    assert row["clipped"] is True
    assert "left_out_of_bounds" in row["issues"]


# Input: Einzelmodus- und Vergleichszeilen; Output: unterdrückte bzw. globale
# Plotdateien.
# Summary/Manifest-Flagge und stabile Plotnamen sichern die Entscheidung ab.
def test_write_outputs_suppresses_uncomparable_comparison(tmp_path: Path) -> None:
    payload = {"run_id": "r", "placement_mode": "corners"}
    row = extract_box_metrics(
        Path("x"), payload, 100, 100, _annotation(0, 0, 10, 10), 0
    )
    output = tmp_path / "out"
    write_analysis_outputs(
        [row], [summarize_run([row])], output, {"unbalanced_groups": [{}]}, 4
    )
    summary = json.loads((output / "descriptive_summary.json").read_text())
    manifest = json.loads((output / "analysis_manifest.json").read_text())
    assert summary["mode_comparison_suppressed"] is True
    assert manifest["mode_comparison_suppressed"] is True
    assert (output / "plots" / "config_000" / "hist_center_x_corners.png").is_file()
    assert not (output / "plots" / "hist_center_x.png").is_file()


# Input: Je ein Run beider Modi mit identischer Konfiguration; Output: Vergleichsplots.
# Ein vollständiger Modussatz erlaubt die globalen, überlagerten Diagramme.
def test_write_outputs_creates_comparison_plots(tmp_path: Path) -> None:
    rows = []
    run_rows = []
    for mode in ("corners", "free"):
        payload = {
            "run_id": mode,
            "placement_mode": mode,
            "rotation": 0,
            "document_type": "jpg",
            "font": "arial",
            "font_size": 100,
        }
        row = extract_box_metrics(
            Path("x"), payload, 100, 100, _annotation(0, 0, 10, 10), 0
        )
        rows.append(row)
        run_rows.append(summarize_run([row]))
    extra_payload = {
        "run_id": "extra",
        "placement_mode": "corners",
        "rotation": 90,
        "font_size": 80,
    }
    extra = extract_box_metrics(
        Path("x"), extra_payload, 100, 100, _annotation(10, 10, 20, 20), 0
    )
    rows.append(extra)
    run_rows.append(summarize_run([extra]))
    output = tmp_path / "out"
    write_analysis_outputs(rows, run_rows, output, {"unbalanced_groups": []}, 4)
    summary = json.loads((output / "descriptive_summary.json").read_text())
    manifest = json.loads((output / "analysis_manifest.json").read_text())
    assert summary["mode_comparison_suppressed"] is False
    assert manifest["comparable_configuration_count"] == 1
    assert (output / "plots" / "hist_center_x.png").is_file()
    assert "analysis_manifest.json" in manifest["outputs"]
    assert "plots/" in manifest["outputs"]
    assert "plots/hist_center_x.png" in manifest["plot_files"]


# Input: Beide Modi mit leeren Konfigurationsfeldern; Output: unterdrückter Vergleich.
# Boolwert und Anzahl müssen dieselbe Vollständigkeitsprüfung verwenden.
def test_empty_configuration_fields_suppress_comparison(tmp_path: Path) -> None:
    rows = []
    run_rows = []
    for mode in ("corners", "free"):
        payload = {"run_id": mode, "placement_mode": mode}
        row = extract_box_metrics(
            Path("x"), payload, 100, 100, _annotation(0, 0, 10, 10), 0
        )
        rows.append(row)
        run_rows.append(summarize_run([row]))
    output = tmp_path / "out"
    write_analysis_outputs(rows, run_rows, output, {"unbalanced_groups": []}, 4)
    summary = json.loads((output / "descriptive_summary.json").read_text())
    manifest = json.loads((output / "analysis_manifest.json").read_text())
    assert summary["mode_comparison_suppressed"] is True
    assert manifest["mode_comparison_suppressed"] is True
    assert manifest["comparable_configuration_count"] == 0
    assert "plots/hist_center_x.png" not in manifest["plot_files"]


# Input: Boxzeilen aus genau einem Placement-Modus; Output: Unbalance-Befund
# auf Run-Ebene.
# Der vollständige Konfigurationsschlüssel und der fehlende Modus werden ausgewiesen.
def test_unbalanced_groups_counts_runs_and_missing_mode() -> None:
    payload = {
        "run_id": "r",
        "placement_mode": "corners",
        "rotation": 90,
        "document_type": "jpg",
        "font": "arial",
        "font_size": 100,
    }
    rows = [
        extract_box_metrics(Path("x"), payload, 100, 100, _annotation(0, 0, 10, 10), 0)
    ]
    findings = _unbalanced_groups(rows)
    assert len(findings) == 1
    assert findings[0]["run_counts"] == {"corners": 1, "free": 0}
    assert findings[0]["configuration"]["rotation"] == "90"


# Input: Zwei bereits deduplizierte Runzeilen mit gleicher Run-ID.
# Output: Beide Runs werden gezählt und nicht nochmals anhand der Run-ID verschmolzen.
# Der Regressionstest schützt die Run-Level-Auswertung vor einer zweiten Deduplizierung.
def test_unbalanced_groups_counts_same_run_id_as_two_runs() -> None:
    base = {
        "run_id": "same-id",
        "placement_mode": "corners",
        "rotation": 90,
        "document_type": "jpg",
        "font": "arial",
        "font_size": 100,
        "width": 100,
        "height": 100,
    }
    findings = _unbalanced_groups(
        [
            {**base, "run_fingerprint": "one"},
            {**base, "run_fingerprint": "two"},
        ]
    )
    assert findings[0]["run_counts"] == {"corners": 2, "free": 0}


# Input: Leeres rekursives Eingabeverzeichnis; Output: vollständiger leerer
# Ergebnisbaum.
# Leere Eingaben bleiben erfolgreich und liefern leere CSVs sowie ein Manifest.
def test_analyze_empty_input(tmp_path: Path) -> None:
    result = analyze_paths(tmp_path / "input", tmp_path / "out", "empty", 4, 100, 100)
    assert (result / "box_metrics.csv").is_file()
    assert (
        json.loads((result / "descriptive_summary.json").read_text())["box_count"] == 0
    )


# Input: JPG-, DICOM- und Output-Referenzen.
# Output: Formatbewusste Dimensionen mit Quellenkennzeichnung.
# Die Tests decken die drei nicht-Fallback-Dimensionsquellen ab.
def test_image_dimensions_supports_jpeg_dicom_and_output(tmp_path: Path) -> None:
    import pydicom
    from PIL import Image
    from pydicom.dataset import FileDataset, FileMetaDataset

    ground_truth = tmp_path / "ground_truth.json"
    jpg = tmp_path / "source.jpeg"
    Image.new("RGB", (17, 9)).save(jpg)
    assert image_dimensions_with_source(ground_truth, {"source_file": jpg.name}) == {
        "width": 17.0,
        "height": 9.0,
        "source": "source_file",
    }
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = pydicom.uid.SecondaryCaptureImageStorage
    meta.MediaStorageSOPInstanceUID = pydicom.uid.generate_uid()
    meta.TransferSyntaxUID = pydicom.uid.ExplicitVRLittleEndian
    dicom = FileDataset(
        str(tmp_path / "output.dcm"), {}, file_meta=meta, preamble=b"\0" * 128
    )
    dicom.Rows, dicom.Columns = 23, 31
    dicom.save_as(dicom.filename)
    assert image_dimensions_with_source(
        ground_truth, {"output_file": "output.dcm"}
    ) == {"width": 31.0, "height": 23.0, "source": "output_file"}


# Input: Vorhandene, ungültige DICOM-Datei ohne Fallback.
# Output: Fehlende Dimensionen statt einer pydicom-Ausnahme.
# Die Analyse protokolliert anschließend den Pfad und die fehlende
# Dimensionsinformation.
def test_invalid_dicom_is_skipped_with_dimension_reason(tmp_path: Path) -> None:
    path = tmp_path / "ground_truth.json"
    dicom = tmp_path / "broken.dcm"
    dicom.write_bytes(b"not a dicom")
    result = image_dimensions_with_source(path, {"source_file": dicom.name})
    assert result["width"] is None
    assert "source_file:invalid_dicom" in result["missing_information"]
    output = tmp_path / "analysis"
    analyze_payloads(
        [
            (
                path,
                {
                    "source_file": dicom.name,
                    "box_annotations": [_annotation(0, 0, 1, 1)],
                },
            )
        ],
        output,
        4,
    )
    manifest = json.loads((output / "analysis_manifest.json").read_text())
    assert manifest["skipped_runs"][0]["path"].endswith("ground_truth.json")
    assert (
        "source_file:invalid_dicom"
        in manifest["skipped_runs"][0]["missing_information"]
    )


# Input: Identische Ground Truths in zwei Pfaden.
# Output: Ein ausgewerteter Run und ein Duplikatmanifest.
# Run-ID und Dateipfad dürfen die Deduplizierung nicht beeinflussen.
def test_analyze_payloads_deduplicates_runs_and_counts_manifest(tmp_path: Path) -> None:
    payload = {
        "run_id": "different",
        "seed": 4,
        "placement_mode": "corners",
        "document_type": "jpg",
        "rotation": 0,
        "font": "arial",
        "font_size": 100,
        "box_annotations": [_annotation(0, 0, 10, 10)],
    }
    paths = []
    for name in ("one", "two"):
        folder = tmp_path / name
        folder.mkdir()
        (folder / "preview.png").write_bytes(b"not-an-image")
        path = folder / "ground_truth.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        paths.append((path, payload))
    output = tmp_path / "analysis"
    analyze_payloads(paths, output, 4, 100, 100)
    manifest = json.loads((output / "analysis_manifest.json").read_text())
    assert manifest["found_run_count"] == 2
    assert manifest["evaluated_run_count"] == manifest["unique_run_count"] == 1
    assert manifest["duplicate_run_count"] == 1
    assert len(manifest["duplicate_runs"][0]["files"]) == 2


# Input: Endliche Kennzahlenwerte.
# Output: Vollständige deskriptive Statistik inklusive Perzentilen.
# IQR und p05/p95 werden deterministisch linear interpoliert.
def test_descriptive_statistics_contains_required_values() -> None:
    result = descriptive_statistics([1, 2, 3, 4, 5])
    assert result["n"] == 5
    assert result["mean"] == 3
    assert result["median"] == 3
    assert result["iqr"] == 2
    assert result["p05"] == pytest.approx(1.2)
    assert result["p95"] == pytest.approx(4.8)


# Input: Ein Run mit gültigen und ungültigen Annotationen.
# Output: Gültige Boxzeile sowie auditierte Fehler mit Originalindex.
# Einzelne fehlerhafte Annotationen dürfen den gesamten Run nicht abbrechen.
def test_mixed_invalid_annotations_are_audited(tmp_path: Path) -> None:
    payload = {
        "run_id": "mixed",
        "placement_mode": "corners",
        "box_annotations": [
            _annotation(0, 0, 10, 10),
            {"label": "missing"},
            {"corners": [{"x": 1, "y": 1}]},
            "not-an-annotation",
        ],
    }
    output = tmp_path / "analysis"
    analyze_payloads([(tmp_path / "ground_truth.json", payload)], output, 4, 100, 100)
    manifest = json.loads((output / "analysis_manifest.json").read_text())
    skips = manifest["skipped_runs"]
    assert manifest["evaluated_box_count"] == 1
    assert {skip["annotation_index"] for skip in skips} == {1, 2, 3}
    assert all(skip["path"].endswith("ground_truth.json") for skip in skips)
    assert {skip["reason"] for skip in skips} == {
        "missing_corners",
        "invalid_corners",
        "invalid_annotation",
    }


# Input: Ein Run mit vollständig ungültiger Annotation.
# Output: Kein ausgewerteter Run und ein nachvollziehbarer Skipgrund.
# Die Analyse bleibt erfolgreich und schreibt trotzdem alle Audit-Artefakte.
def test_invalid_annotation_does_not_abort_analysis(tmp_path: Path) -> None:
    payload = {"box_annotations": [{"corners": [{"x": 1, "y": 1}]}]}
    output = tmp_path / "analysis"
    analyze_payloads([(tmp_path / "ground_truth.json", payload)], output, 4, 100, 100)
    manifest = json.loads((output / "analysis_manifest.json").read_text())
    assert manifest["evaluated_run_count"] == 0
    assert manifest["skipped_runs"][0]["annotation_index"] == 0


# Input: Balancierte Vergleichskonfiguration.
# Output: vollständige globale und getrennte Plotfamilien.
# Globale Dateien werden nur für die gemeinsame Konfiguration geschrieben und
# enthalten n im Titel.
def test_comparable_plots_include_histograms_boxplots_and_scatter(
    tmp_path: Path,
) -> None:
    rows = []
    runs = []
    for mode in ("corners", "free"):
        payload = {
            "run_id": mode,
            "placement_mode": mode,
            "rotation": 0,
            "document_type": "jpg",
            "font": "arial",
            "font_size": 100,
        }
        row = extract_box_metrics(
            Path("x"), payload, 100, 100, _annotation(0, 0, 10, 10), 0
        )
        rows.append(row)
        runs.append(summarize_run([row]))
    output = tmp_path / "analysis"
    write_analysis_outputs(rows, runs, output, {"unbalanced_groups": []}, 4)
    plots = output / "plots"
    assert (plots / "hist_center_x.png").is_file()
    assert (plots / "boxplot_normalized_area.png").is_file()
    assert (plots / "scatter_centers.png").is_file()
    manifest = json.loads((output / "analysis_manifest.json").read_text())
    assert len(manifest["comparable_configurations"]) == 1


# Input: Kommando-Template mit Pfaden, die Leerzeichen enthalten, und Konfiguration.
# Output: Tokenisiertes argv ohne Pfadzerlegung und mit tatsächlich übergebenem
# Config-Token.
# Die Ersetzung erfolgt vor dem Split über Sentinelwerte.
def test_render_command_preserves_paths_and_uses_configuration() -> None:
    command = render_command(
        "python runner.py --input {input} --output {output_dir} "
        "--config {configuration} --mode {mode}",
        7,
        "corners",
        Path("C:/data set/run output"),
        Path("C:/data set/source.jpg"),
        {"font": "arial"},
    )
    assert command[command.index("--input") + 1] == str(Path("C:/data set/source.jpg"))
    assert command[command.index("--output") + 1] == str(Path("C:/data set/run output"))
    assert json.loads(command[command.index("--config") + 1]) == {"font": "arial"}


# Input: Nichtleere Konfiguration ohne Config-Platzhalter.
# Output: Expliziter Validierungsfehler statt einer nur behaupteten Konfiguration.
def test_render_command_requires_configuration_placeholder() -> None:
    with pytest.raises(ValueError, match="configuration"):
        render_command(
            "python runner.py --mode {mode}",
            1,
            "free",
            Path("out"),
            Path("in"),
            {"font": "arial"},
        )


# Input: Vergleichbare Boxzeilen beider Modi und feste Binningparameter.
# Output: Identische Heatmap-Achsen, Bins und gemeinsame Farbobergrenze.
# Die Hilfsfunktion macht die Fairnessregel ohne Bildpixel- oder Backendprüfung testbar.
def test_comparable_heatmaps_share_parameters() -> None:
    rows = []
    for mode, left in (("corners", 0), ("free", 50)):
        payload = {
            "placement_mode": mode,
            "rotation": 0,
            "document_type": "jpg",
            "font": "arial",
            "font_size": 100,
        }
        rows.append(
            extract_box_metrics(
                Path("x"), payload, 100, 100, _annotation(left, 0, left + 10, 10), 0
            )
        )
    key = ("0", "jpg", "100", "100", "arial", "100")
    result = heatmap_parameters(rows, {key}, 4)
    assert result["bins"] == 4
    assert result["range"] == ((0.0, 1.0), (0.0, 1.0))
    assert result["vmax"] == max(
        cell for matrix in result["counts"].values() for line in matrix for cell in line
    )
    assert set(result["counts"]) == {"corners", "free"}
