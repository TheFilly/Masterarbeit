# `pixel_injection.py` Decomposition & Typing-Debt Retirement (WP-E)

Status: core decomposition completed 2026-07-12. Two non-blocking items remain:
internal renderer payload typing and the compatibility-shim decision.

## Headline finding: the typing debt is smaller than advertised

The `pyproject.toml` TODO says typing waits for "the document model replacing
dict payloads" (phase-2). Measured reality: running strict mypy on the module
*without* the override produces **exactly 13 errors, none of which involve the
dict payloads**. All 13 are PIL/numpy typing issues fixable today,
byte-identically, without WP-B. The override can be retired *before* the
decomposition or the domain model. (Verified 2026-07-06 with the repo's mypy
against `main`.)

## Implementation status, 2026-07-12

Implemented:

- `pyproject.toml` no longer has a `tool.mypy.overrides` block for the engine.
- Engine responsibilities live in `frames.py`, `fonts.py`, `geometry.py`,
  `segments.py`, `overlay.py`, `handwriting.py`, `placement.py`, and
  `injector.py`.
- `pixel_injection.py` re-exports the legacy surface for compatibility.
- `_write_pixel_array` lives in `writers/dicom.py`.
- The dead public helpers `build_visible_text_annotations` and
  `render_annotations_for_dataset` are gone.

Open:

- `dict[str, Any]` renderer payloads remain in internal engine seams; replacing
  them with smaller internal models can wait for a behavior-preserving cleanup.

## Typing-debt inventory (complete)

| # | Line(s) | Error code | Cause | Fix (behaviour-neutral) |
|---|---|---|---|---|
| 1 | 44, 48 | `no-any-return` | `pixel_array[0]` / `pixel_array` returns `Any` after ndarray indexing in `extract_preview_frame` | wrap returns in `np.asarray(...)` (already the input idiom at line 42) |
| 2 | 65 | `no-any-return` | `np.clip(...).astype(np.uint8)` inferred `Any` in `normalize_to_uint8` | annotate intermediate as `npt.NDArray[np.uint8]` or wrap in `np.asarray(..., dtype=np.uint8)` |
| 3 | 546, 562, 572, 573 | `arg-type` | `Image.new("...", (base_width, base_height))` — sizes inferred `int \| float` because `font.getbbox` stubs return floats and `max(1, right - left)` propagates them (`_prepare_annotation_overlay`) | coerce once at the source: `text_width = max(1, int(right - left))`, `text_height = max(1, int(bottom - top))` (lines 540-541); values are already whole numbers for both font classes |
| 4 | 587, 588, 589, 591, 662, 663 | `attr-defined` | `Image.BICUBIC` — removed from Pillow stubs; runtime alias of `Image.Resampling.BICUBIC` | replace all six occurrences with `Image.Resampling.BICUBIC` (identical enum value; resampling output unchanged) |

Retirement is a 3-line-cluster patch + deleting the `[[tool.mypy.overrides]]`
block. Add a regression guard: CI fails if any new per-module override
appears.

Note on fix 3: `text_origin = (padding - left, padding - top)` (line 544) also
becomes float-typed from the same source; PIL accepts float text origins, and
mypy does not flag it — coercing `left/top` to `int` in the same place keeps
origin arithmetic exactly as today (getbbox returns whole numbers for
truetype fonts at integer sizes; assert-cast rather than round to make any
future non-integer case loud).

## Current function inventory → module split

Six concerns share the file today. Proposed split under `engine/`:

| New module | Functions (current line) | Concern |
|---|---|---|
| `frames.py` | `extract_preview_frame` (41), `normalize_to_uint8` (53), `frame_to_image` (69), `save_preview_image` (186) | frame extraction & image conversion |
| `fonts.py` | `_FONT_PATHS` (19), `load_default_font` (77), `_resolve_font_size_px` (32), `_DEFAULT_FONT_SIZE_PX` (17) | font resolution (WP-C/config later externalizes paths; ADR-0002) |
| `geometry.py` | `_validate_rotation` (853) + `ALLOWED_ROTATIONS_DEGREES` (15), `_coerce_position` (843), `_estimate_rotated_size` (788), `_rotated_corners` (865), `_mask_bounds_to_corners` (1048), `_thresholded_mask_bounds` (1086) + `_MASK_ALPHA_THRESHOLD` (28), `_require_mask_bounds` (1020), `_serialize_mask_bounds` (1031) | rotated-corner math & mask bounds |
| `segments.py` | `_normalize_text_segments` (907), `_draw_segment_masks` (935), `_split_prefix_and_pii_text` (984), `_resolve_segment_draw_bounds` (1002) | PII/generic segment handling |
| `overlay.py` | `_prepare_annotation_overlay` (509), `_render_single_annotation` (388), `render_visible_annotations` (144) | font-text overlay rendering |
| `handwriting.py` | `_prepare_handwriting_asset_overlay` (648), `_render_handwriting_annotation` (453) | handwriting-asset overlay rendering |
| `placement.py` | `_materialize_positions` (707), `_VALID_PLACEMENT_MODES` (18) | seeded position selection |
| `injector.py` | `inject_visible_text` (196), `inject_visible_text_into_image` (243), `_inject_visible_text_into_frame` (280), `_render_frame_with_annotations` (488), `_build_box_annotation` (1067), `_TEXT_BACKGROUND_COLORS` (25) | orchestration facade the runner calls |
| `writers/dicom.py` (move out of engine) | `_write_pixel_array` (803) | DICOM pixel writeback is a *writer* concern: it rewrites transfer syntax, photometric interpretation, and frame metadata — format conformance, not rendering (aligns with ADR-0006; the DICOM writer owns dataset mutation for persistence) |
| deleted | `build_visible_text_annotations` (99), `render_annotations_for_dataset` (169) | dead API duplicating prefix taxonomy |

Import direction (no cycles):
`injector → placement → overlay/handwriting → segments → geometry/fonts/frames`.
`overlay` and `handwriting` both depend on `geometry` + `segments`;
`placement` calls `overlay._prepare_annotation_overlay` for sizing — that
cross-dependency is intrinsic (placement must measure what rendering will
draw, per the comment at line 703-706) and stays explicit.

Circular-dependency hazard: `_prepare_annotation_overlay` dispatches to
`_prepare_handwriting_asset_overlay` when `renderer_type == "handwriting_asset"`
(line 516). Invert it: the *caller* (`_render_single_annotation`,
`_materialize_positions`) dispatches on `renderer_type` to the right module,
so `overlay` never imports `handwriting`. Behaviour identical — the dispatch
happens one frame earlier.

## Sequencing

1. **Retire the override first** (independent of everything): apply the 13
   fixes, delete the `pyproject.toml` block, run byte-identity harness
   (WP-D step 0) — resampling enum and int coercions must not change a pixel.
2. Move `geometry.py` + `fonts.py` + `frames.py` (leaf modules, no in-repo
   dependents besides the engine itself); keep re-exports in
   `pixel_injection.py`.
3. Move `segments.py`, then `overlay.py` + `handwriting.py` (with the
   dispatch inversion), then `placement.py`.
4. Move the facade into `injector.py`; `pixel_injection.py` becomes a
   re-export shim; update `tests/unit/test_pixel_injection_corners.py:14-21`
   and `tests/unit/test_handwriting_asset_rendering.py:8-11` imports; delete
   the shim once `engine/__init__.py` exports the public surface.
5. Move `_write_pixel_array` into the DICOM writer when WP-F lands (it is the
   only engine function touching pydicom datasets besides the facade).
6. Delete the dead API (`build_visible_text_annotations`,
   `render_annotations_for_dataset`) and its `engine/__init__.py` exports.

Each step: pytest green + byte-identity harness. Steps 1-4 need no WP-B
types; when WP-B lands, `dict[str, Any]` parameters
(`annotation`, `visible_injections`, overlay payload) upgrade to
`RenderPlanItem` / `PlacedRenderItem` / `RenderedAnnotation` — the overlay
payload dict (lines 595-642) is the best candidate for a small internal
`OverlaySpec` model since it crosses the overlay→render seam.

## Testability payoff

- `geometry.py` and `segments.py` become pure-function modules — property
  tests (corner order under all five rotations, segment reconstruction) get
  trivial.
- `placement.py` isolates the only RNG consumer in the engine, making the
  WP-G "named stream" change a one-module diff.
- `injector.py` is the only module the runner (later: adapters) may import.

## Implementation Status

### Implemented 2026-07-12

- Typing fixes landed and the mypy override was deleted.
- Engine modules were split in the order above; `pixel_injection.py` remains as
  a compatibility export shim.
- Handwriting dispatch no longer creates an `overlay` to `handwriting` import.
- Dead public helpers were removed after repo-wide reference checks.
- `_write_pixel_array` moved into the DICOM writer during WP-F.

### Remaining

- Internal renderer payloads still use `dict[str, Any]` in a few engine seams.
- Keeping or deleting the `pixel_injection.py` compatibility shim needs a later
  compatibility decision.

Definition of done update: strict mypy runs without per-module overrides, the
engine has cohesive modules, and the committed E2E harness covers byte-stable
DCM/JPG output.
