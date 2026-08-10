# ADR-0010: Dynamic handwriting appearance from canonical masks

## Status

Accepted

## Context

DICOM and JPG frames can contain both dark and bright regions. A handwriting
asset with a generator-baked ink color is therefore not reliably readable, and
creating separate black/white assets multiplies cache entries without changing
the handwriting shape.

## Decision

The separate handwriting mask is the canonical visual source. The renderer
reconstructs the RGBA ink layer at the final position and samples the
display-mapped RGB frame only under the rotated mask.

- Auto mode selects white below median luminance `128` and black otherwise.
- A p10-p90 spread above `96`, contrast below `64`, or fewer than eight valid
  samples activates a two-pixel halo.
- No valid samples use white ink with a black halo.
- Explicit black, gray, or white overrides bypass automatic color selection.
- The halo is visual only; ground truth continues to use the original ink mask.
- Generator cache identity excludes legacy presentation fields `ink_color` and
  `background`; the renderer version is bumped for incompatible old bundles.

## Consequences

Color changes do not require regenerated handwriting assets. Render metadata
records the selected color, actual contrast mode, luminance statistics, and
decision reason. Legacy manifests remain readable, but their baked image color
or background no longer controls the canonical render path.
