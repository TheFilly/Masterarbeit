# Research Documentation

This directory separates working plans from evidence, findings, and stable decisions.

- `research/` contains phase-specific observations, summaries, matrices, and open questions.
- `decisions/` contains stable architecture or scope decisions.
- `thesis/` maps findings and decisions to thesis claims and chapters.
- `templates/` contains reusable authoring templates.

Rule of thumb:

- Record uncertain or exploratory statements as findings.
- Promote only reviewed and stable outcomes to decisions.
- Link thesis claims back to findings and decisions.

Reading order for agents and collaborators:

1. Read the relevant phase `summary.md` first.
2. Read `open-questions.md` for unresolved issues that may affect the task.
3. Read only the findings, evidence, or decisions that are directly linked to the task.
4. Treat accepted decisions as more stable than draft findings.

Context discipline:

- Do not read the entire `docs/` tree by default.
- Use summaries as the canonical snapshot of the current state.
- Use findings as atomic evidence records.
- Use decisions as the durable source of project truth once accepted.
- If summaries lag behind findings, update the summary instead of relying on hidden divergence.
