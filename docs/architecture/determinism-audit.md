# Reproducibility & Determinism Audit (WP-G)

Status: seed and clock remediation completed 2026-07-12; environment provenance
remains open behind ADR-0008. This audit is the basis for ADR-0009 and covers
randomness, clocks, and environment dependencies in `src/injection_pipeline/`.

Verdicts: **violation** breaks the principle, **intended** is documented
prototype behavior, **honoured** is seeded or deterministic, **environment** is
a reproducibility input outside random draws.

## Inventory

| # | Source | Location | Verdict | Remedy / status |
|---|---|---|---|---|
| N1 | Default-input selection | `inputs.py` | **honoured** | Fixed in WP-G. `select_seeded_default_input()` sorts candidates and draws with `random.Random(derive_seed(seed, "input_selection"))`. |
| N2 | Wall-clock timestamp in `run_id` | `runner.py`, `cli.py` | **honoured** | Fixed in WP-G. `run(args, now=...)` accepts an injected clock; CLI exposes `--run-timestamp` as ISO-8601. |
| N3 | Faker identity generation | `identity/generator.py` | **honoured** | Kept direct `Faker.seed_instance(seed)` semantics for `identity_a`; field order remains load-bearing. Faker package and locale data still belong in future environment provenance. See N14 for a platform-specific exception found in the DOB recipe. |
| N4 | Unused second identity | `runner.py` | **removed** | WP-R removed `identity_b` generation and its stdout-only output on 2026-07-13. |
| N5 | Placement RNG | `engine/pixel_injection.py`, `engine/injector.py` | **honoured** | Grandfathered by ADR-0009 as `"placement/raw-seed"`. Migrating to `derive_seed()` would move pixels and needs a future byte-compat ADR. |
| N6 | Directory iteration order | `inputs.py` | **honoured** | Candidate collection and seeded selection both sort by lowercase path string. |
| N7 | Font files | `engine/fonts.py`, pixel rendering | **environment** | Font path and file hash still need RunRecord provenance after ADR-0008 opens a compatible emitted version. |
| N8 | Pillow rendering & resampling | pixel rendering and JPG encode | **honoured** (layout engine); **environment** (rest) | `load_default_font()` pins `layout_engine=ImageFont.Layout.BASIC` as a defensive fix (2026-07-14): Pillow otherwise auto-selects `RAQM` shaping whenever the installed wheel bundles `libraqm`, a per-platform-wheel property, not a Pillow-version property. Verified via a Windows-vs-Linux (Docker) A/B comparison on 2026-07-14 that rendered `box_annotations`/mask bounds and the injected `synthetic_injected.{dcm,jpg}` bytes are already byte-identical across platforms with this pin; N14 was the actual cause of the E2E record-hash break, not glyph shaping. Remaining resampling/version provenance still waits for ADR-0008. |
| N9 | matplotlib previews | `writers/preview.py` | **environment** | Rendered pixels verified byte-identical across Windows/Linux (2026-07-14, pixel diff = 0), but the PNG container bytes are not: platform-specific Pillow/matplotlib Agg builds re-encode identical pixels to different compressed bytes. E2E binary reference hashes for `preview.png`/`preview_annotated.png` are pinned to the CI (ubuntu-latest) encoding for this reason. Library-version provenance still waits for ADR-0008. |
| N10 | Library versions as inputs | run environment | **environment** | Still open. ADR-0008 has no conflict-free emitted RunRecord version for additive `reproducibility` fields. |
| N11 | numpy randomness | `src/` | **honoured** | No `np.random` use in the package. |
| N12 | pydicom write path | `writers/dicom.py` | **honoured** | Deterministic for fixed input and pydicom. SOPInstanceUID reuse remains out of determinism scope. |
| N13 | Interactive input prompts | `cli.py` | **intended** | Human choices land in `args`; interactive mode now also accepts optional `run-timestamp`. |
| N14 | Faker `date_of_birth()` calendar day | `identity/recipes.py` | **honoured** | The identifier schema carries `generator.reference_date = "2026-07-10"` plus `reference_date_policy`; DOB generation no longer reads the system date. Fixed again 2026-07-14: the recipe called `fake.date_time_ad()`, whose `_rand_seconds` helper (`faker/providers/date_time/__init__.py`) branches on `platform.system()` itself — `randint` (int seconds) on Windows, `uniform` (float seconds) elsewhere — consuming the seeded RNG stream differently per OS and yielding a different birth date for the same seed. This was the actual cause of the Windows-vs-Linux E2E record-hash mismatch (all other identity fields and box geometry were already platform-stable). The recipe now draws `fake.random.randint()` directly instead of delegating to `fake.date_time_ad()`, matching Faker's former Windows-only behavior on every platform. `identity_id`-independent unit coverage (`test_date_of_birth_matches_reference_day_faker_path_and_ignores_execution_day`) was updated to cross-check against the same platform-independent primitives instead of `fake.date_of_birth()`, which still carries the OS branch and can no longer serve as a cross-platform reference. |

`derive_seed(seed, name)` is the first eight bytes of
`sha256(f"{seed}:{name}".encode("utf-8"))` as a big-endian integer. Python's
built-in `hash()` must not be used for seed derivation.

## Reproducibility contract

For a fixed code version, dependency lockfile, font files, and input document,
an injection run is a pure function of `(seed, input, rotation, placement_mode,
font_size_pct, font_family, text_background, identifier_schema,
run_timestamp)`. Injected values, rendered pixels, annotation geometry, and
ground-truth artifacts are byte-identical across repeated runs.

Every new random decision uses a named stream derived from the run seed and a
stage name. `identity_a` keeps direct Faker seeding and placement keeps the
grandfathered raw-seed stream for byte compatibility. Auto-selection of a
default input is seeded and records the resolved path, so a run can be replayed
by passing that path.

Future RunRecord versions should record environmental inputs that can influence
bytes: library versions, platform, font paths, and font file hashes.

## Current open gate

The `reproducibility` block and identifier-schema provenance are additive
RunRecord fields. ADR-0008 still has no conflict-free emitted version beyond
`0.2.0-prototype`, so WP-G does not emit partial or version-incorrect fields.

## Reference updates

E2E now passes a fixed timestamp and compares full artifact bytes, including
`ground_truth.json` and `run_manifest.json`. Reference hash changes are limited
to the DOB fix and timestamp fix:

- DCM output bytes changed because `PatientBirthDate` no longer drifts with the
  execution day.
- JSON artifact bytes changed because `run_id` now uses the fixed E2E
  timestamp instead of a normalized wall-clock value.
- Preview image bytes stayed unchanged because DOB is tag-only in the prototype
  schema.

Reference update 2026-07-14 (see N14): `patient_birth_date` changed on Linux
because Faker's own `_rand_seconds` branches on `platform.system()`; the DOB
recipe no longer depends on that branch, and the DCM/JPG record hashes are
back to the pre-existing Windows-computed value now that both platforms agree.
`ground_truth.json`, `run_manifest.json`, `preview.png`, and
`preview_annotated.png` reference hashes were re-pinned to the bytes produced
on the CI runner (ubuntu-latest): the JSON files intentionally embed
`os.linesep`, and the PNGs are pixel-identical across platforms but re-encoded
by a platform-specific Pillow/matplotlib build (see N8, N9). Verified locally
via a `ghcr.io/astral-sh/uv:python3.13-bookworm` container reproducing the CI
lint/type-check/test steps.
