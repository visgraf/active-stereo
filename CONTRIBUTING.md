# Contributing

## Before you write code

Open an issue. For experiments, use the Experiment template and fill in the
hypothesis and acceptance criteria **before** any code exists. The discipline is
the point: criteria written after you have seen the result are not criteria.

## Branches

`feat/…`, `fix/…`, `exp/NNN-…`, `docs/…`. Never commit to `main`.

## Definition of done

- `pytest -q` passes
- New behaviour has a test; a fixed bug has a **regression** test
- Public functions document units and frames
- An ADR is filed if the decision constrains future work
- The diff contains nothing that was not asked for

## Tests

`tests/unit/` pins contracts. `tests/regression/` pins lessons — each file names
the ADR it defends and states the symptom that was originally observed.

Never weaken a test, loosen a tolerance, or add `xfail` to make a suite green.
A failing test is information about the code, not an obstacle to the commit.

## Dependencies

Justify each one against what NumPy already does. This codebase must still build
in five years.

## ADRs

Append-only. Superseding means writing a new ADR that references the old one.
The **Alternatives considered** section is the part that will matter later.
