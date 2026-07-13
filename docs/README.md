# Documentation

`docs/` stores architecture notes, decisions, operational documentation, and
status material. Keep raw notes out of `PLAN.md`; promote stable choices into
decisions.

## Directories

- `decisions/`: accepted or proposed architecture and scope decisions.
- `architecture/`: current specifications, active audits, and implementation
  status. Completed one-off handoff plans are removed after their durable
  decisions and results are captured elsewhere.
- `archive/`: superseded material. Do not cite it as current evidence.

## Reading Order

1. Read the relevant architecture or operational doc.
2. Read linked ADRs in `docs/decisions/`.
3. Open only directly linked code, tests, or archived context.
4. Treat `docs/archive/` as historical context unless a current doc cites it.

Accepted decisions outrank design notes. If an architecture note and an ADR
disagree, update the note or write a superseding ADR instead of blending both
states.
