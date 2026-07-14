---
id: ADR-0009
status: accepted
based_on:
  - docs/architecture/determinism-audit.md
---

# ADR-0009: Determinism contract - named seeded streams, injectable clock, recorded environment

## Context

"Seed all randomness" (`AGENTS.md`) had two documented violations: unseeded
default-input selection and a wall-clock `run_id`. Identity B used `seed + 1`,
which made `run(seed=42)`'s second identity equal `run(seed=43)`'s injected
identity. Faker `date_of_birth()` also used the execution day as an implicit
input, so a fixed seed could drift across calendar days.

The full inventory is `docs/architecture/determinism-audit.md`.

## Decision

Adopt the reproducibility contract specified in the determinism audit, with the
compatibility exceptions below:

1. Every new random draw comes from a **named stream** derived from the run seed
   via SHA-256 (for example,
   `derive_seed(seed, "input_selection")`). Code must not use module-level
   `random`.
2. **Clocks are injectable.** `run()` accepts a timestamp and the CLI exposes
   `--run-timestamp` as an ISO-8601 override.
3. **Input selection is seeded.** Default-input choice uses the
   `input_selection` stream over the sorted candidate list. The resolved input
   path remains recorded in `source_file`.
4. **Identity A keeps direct Faker seeding.** `generate_identity(seed, schema)`
   keeps `Faker.seed_instance(seed)` for the injected identity, so WP-C identity
   bytes stay stable.
5. **Placement keeps the raw seed.** The placement RNG is the grandfathered
   `"placement/raw-seed"` stream. Migrating it to `derive_seed()` would move
   pixels and needs a future byte-compat ADR.
6. **Environment recording waits for ADR-0008.** The desired
   `reproducibility` block and identifier-schema provenance are additive
   RunRecord fields, but no conflict-free emitted RunRecord version exists yet.
   The implementation must not add them to `0.2.0-prototype`.

The identifier schema owns date-sensitive Faker semantics through
`generator.reference_date` and `generator.reference_date_policy`. The prototype
schema fixes `reference_date = "2026-07-10"` to remove Faker
`date_of_birth()`'s execution-day input. As of 2026-07-14 the recipe no longer
calls Faker's `date_of_birth()`/`date_time_ad()` convenience methods at all:
their internal `_rand_seconds` branches on `platform.system()` (`randint` on
Windows, `uniform` elsewhere), which breaks byte-identity across operating
systems for a fixed seed. The recipe now draws the age-window offset via
`fake.random.randint()` directly, matching Faker's former Windows-only
behavior on every platform.

## Alternatives Considered

- **Single shared RNG passed everywhere**: consumption order couples unrelated
  stages. Inserting one draw in identity generation would change placement.
- **Global `random.seed(seed)`**: library code consuming the global stream
  breaks isolation invisibly.
- **Immediate RunRecord environment block**: the fields are additive, but
  ADR-0008 still blocks a conflict-free emitted version.

## Consequences

- At adoption, seed derivation changed `input_selection` and the stdout-only
  `identity_b`; WP-R later removed the unused second identity entirely.
- Placement remains byte-compatible because ADR-0009 grandfathers the raw seed.
- `identity_a` keeps direct Faker seeding, while DOB generation no longer reads
  the system date.
- The thesis methods chapter can cite the contract in
  `docs/architecture/determinism-audit.md`.

## Implementation Status

Implemented 2026-07-12 for random draws and clocks:

- `seeding.derive_seed()` provides named stream seeds.
- `inputs.select_seeded_default_input()` uses the `input_selection` stream over
  sorted candidates.
- `runner.run(args, now=...)` accepts an injected timestamp and the CLI exposes
  `--run-timestamp`.
- Identifier schemas carry `reference_date` and `reference_date_policy`; the
  default schema fixes `2026-07-10`.

The unused `identity_b` generation was removed by WP-R on 2026-07-13. This does
not change the accepted rule that every future random draw uses a named stream.

On 2026-07-14, `identity/recipes.py::date_of_birth` was changed to stop calling
Faker's `date_of_birth()`/`date_time_ad()` convenience methods, because their
internal OS branch broke byte-identity between Windows and Linux for the same
seed (see `docs/architecture/determinism-audit.md` N14). The same date fix
also surfaced a font-resolution gap on `ubuntu-latest` CI (`docs/architecture/
determinism-audit.md` N7/N8) and a pre-existing platform difference in raw
JSON/PNG artifact bytes (line endings, PNG re-encoding) that does not affect
parsed record content; E2E binary reference hashes are now pinned to the CI
(Linux) environment for that reason.

Still open: environment provenance is not emitted because ADR-0008 has not
opened a compatible RunRecord version for additive fields.

## Review Notes

Accepted for WP-G on the WP-B/C/D/E package shape. ADR-0008 still gates
emission of `reproducibility` and identifier-schema provenance fields.
