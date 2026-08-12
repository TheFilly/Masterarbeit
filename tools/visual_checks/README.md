# Visual Checks

This directory contains manually started scripts for visual inspection of
pipeline behavior. These scripts are deliberately outside the automated
pytest suite and may start Docker, write output artifacts, or use local model
weights.

## Full functionality suite

Run from the repository root:

```powershell
uv run python tools/visual_checks/pipeline_functionality.py
```

The script creates a new timestamped directory below
`output/visual-checks/`, so repeated manual runs do not collide with earlier
run bundles. It uses `pathlib` and argument lists instead of shell-specific
path separators or quoting, so the same command works on Windows and macOS.

The suite covers:

- normal DICOM and JPG CLI injection;
- all standard font families, rotations, placement modes, font sizes,
  background modes, and label-box preview options;
- handwriting CLI injection with `auto`, `black`, `gray`, and `white` ink plus
  both contrast modes;
- the standalone `generate-handwriting` command;
- both `inject-pdf` and its `compose-pdf` alias;
- public `inject_function` for native DICOM fields, custom JPG categories,
  DICOM handwriting, and JPG handwriting;
- public `make_pdf` with direct PDF text, multiple images, annotation transfer,
  and a larger layout/flow test.
- focused `test_api.py` and `test_make_pdf_api.py` pytest checks, invoked only
  when this manual suite is started.

Handwriting scenarios require the `injection-scrabblegan` Docker image and the
local checkpoint/source prerequisites. To run the non-handwriting checks only:

```powershell
uv run python tools/visual_checks/pipeline_functionality.py --skip-handwriting
```

Other useful subsets:

```powershell
uv run python tools/visual_checks/pipeline_functionality.py --skip-pdf
uv run python tools/visual_checks/pipeline_functionality.py --skip-api
uv run python tools/visual_checks/pipeline_functionality.py --skip-unit-tests
```

The direct `make_pdf` API currently accepts already rendered image assets and
PDF-native direct text. A direct `handwritten=True` PDF text input remains an
intentional unsupported case and is not included as a successful visual check.

## Individual handwriting alphabet check

For the smaller character-quality check:

```powershell
uv run python tools/visual_checks/handwriting_alphabet.py
```

Generated files belong under `output/` and are not committed.
