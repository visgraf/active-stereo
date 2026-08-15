# ADR-0008: Raise the Python floor to 3.12 and make mypy a blocking gate

- **Status:** Accepted
- **Date:** 2026-08-15
- **Context of discovery:** `mypy src` aborting on numpy's stubs

## Context

`[tool.mypy] python_version = "3.10"` told mypy to parse *everything* with a 3.10
grammar, including third-party stubs. Recent numpy ships `.pyi` files using PEP
695 `type X = ...` statements, which require 3.12. The result was

    numpy/__init__.pyi: error: Type statement is only supported in Python 3.12 and greater

and, critically, `errors prevented further checking` -- the type check was not
merely noisy, it was aborting before reaching our code.

The declared floor was fiction anyway. `requires-python = ">=3.10"` and a CI
matrix of 3.10/3.12 meant the 3.10 job resolved to an older numpy than anyone
develops against, so it tested a configuration that does not exist.

## Decision

1. Remove `python_version` from `[tool.mypy]`. Mypy follows the running
   interpreter, which is the version we actually use.
2. `requires-python = ">=3.12"`; CI matrix `["3.12", "3.14"]` -- the lowest
   supported version and the one in daily use.
3. Annotate the three remaining untyped signatures and make `mypy src` a
   **blocking** CI step by dropping `continue-on-error`.
4. Where a type error points at a real API choice, fix the call rather than
   suppress it. `cv2.StereoSGBM_create` is a module-level alias absent from
   OpenCV's bundled stubs; `cv2.StereoSGBM.create` is the same factory, present
   in the stubs, and needs no ignore. The repo now contains zero `type: ignore`
   comments, enforced by `warn_unused_ignores = true` -- a property worth keeping,
   because each ignore is a place where the checker has been told to stop looking.
   `StereoStimulus.shape` was the other one: unpacking `ndarray.shape` narrows
   `tuple[int, ...]` to a 2-tuple without a cast.

## Alternatives considered

- **Pin `python_version = "3.12"` instead of removing it.** Rejected: it would
  drift out of date the same way, and it buys nothing once the floor is 3.12.
- **Silence the stub with an override or `follow_imports = skip` for numpy.**
  Rejected: it hides a configuration error behind a suppression, and skipping
  numpy's types removes most of the value of running mypy on this codebase.
- **Keep the 3.10 floor and pin an older numpy.** Rejected: freezing numpy for a
  version nobody runs is a real maintenance cost for zero benefit in a lab repo.
- **Leave mypy non-blocking.** Rejected now that it passes. A non-blocking check
  is a check that will be broken within a month.

## Consequences

- Type errors now gate merges, which is one more mechanical guard supporting the
  autonomy ladder in `docs/workflow.md`.
- The repo will not install on 3.10 or 3.11. Acceptable and honest -- it did not
  really work there.
- Raising the floor let ruff apply modernisations it had been suppressing (e.g.
  `datetime.UTC`), so a small unrelated diff landed alongside. Expect that.

## Verification

`mypy src` reports no issues across 32 source files, and the CI `test` job fails
if it ever does again.
