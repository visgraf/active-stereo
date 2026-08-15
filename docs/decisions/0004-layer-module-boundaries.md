# ADR-0004: The six framework layers are the top-level module boundaries

- **Status:** Accepted
- **Date:** 2026-08-15

## Context

The prototype was a single script. Growing it into a multi-year codebase requires
boundaries, and the choice of boundary determines what stays swappable.

## Decision

`src/activestereo/` has exactly six domain packages — `geometry`, `encoding`,
`inference`, `scaling`, `control`, `policy` — matching L1..L6, plus `io`, `viz`,
`utils`. Each layer exposes a `Protocol` for its principal abstraction, so
alternative implementations are drop-in.

The three closures become enforced invariants: no module below L4 returns metres
(scaling closure); L5 consumes estimates with uncertainty and never re-derives
depth (control-regime closure); every public quantity documents its frame
(reference-frame closure).

## Alternatives considered

- **Organise by data type** (`images/`, `fields/`, `filters/`). Rejected: the
  research questions are about layers, so results would cut across modules and
  no boundary would correspond to a claim in the paper.
- **Organise by experiment.** Rejected: guarantees duplication and makes it
  impossible to say what "the framework" is.
- **Flat module.** Rejected: this is the prototype's structure and it is what we
  are migrating away from.

## Consequences

- The code and the paper share a vocabulary, so a reviewer's question maps to a
  directory.
- Cross-layer refactors are more expensive. Accepted: they should be.
- Risk of premature abstraction in `encoding`, which is currently a Protocol with
  no implementation. Accepted deliberately so L3 can be developed against a fixed
  interface before L2 is migrated.

## Verification

`tests/unit/test_inference.py::test_block_matcher_satisfies_protocol` and the
layer-specific unit tests. Import direction is enforced by review, not tooling —
a candidate for a lint rule if it is ever violated.
