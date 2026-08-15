---
description: Draft an ADR for a decision just made
---

Draft an ADR for: $ARGUMENTS

Use `docs/decisions/0000-template.md`. Read the existing ADRs first so numbering
and voice are consistent, and so you can reference any decision this supersedes.

Requirements:

- The **Alternatives considered** section is the point of the document. For each
  alternative, say what it would have bought and why it lost. An ADR with a thin
  alternatives section is worthless in six months.
- If this came from a failure, state the concrete symptom, not just the fix.
- Name the test(s) that pin the decision. If none exist, say so explicitly and
  propose them — an ADR without a test is an intention, not a decision.
- Write it to a new numbered file. **Never edit an existing ADR.**
- Update the table in `docs/decisions/README.md`.
