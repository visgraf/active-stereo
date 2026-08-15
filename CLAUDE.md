# CLAUDE.md — Project Constitution

This file is read automatically by Claude Code at the start of every session.
It is **normative**. When a request conflicts with this file, stop and say so
rather than silently deviating.

---

## 1. What this project is

`active-stereo` is a research codebase implementing a **six-layer framework that
models stereoscopic 3D vision as active Bayesian inference**. The layers, which
are also the top-level module boundaries, are:

| Layer | Module | Concern |
|---|---|---|
| L1 | `geometry` | Generative geometry: rig, projection, Vieth–Müller horopter |
| L2 | `encoding` | Neural encoding: binocular energy model, disparity tuning |
| L3 | `inference` | Disparity-field inference: matchers, MRF/belief propagation |
| L4 | `scaling` | Metric scaling, MLE cue fusion, uncertainty propagation |
| L5 | `control` | Oculomotor control: vergence estimation, Kalman filtering, stability |
| L6 | `policy` | Active sampling: saliency, information-maximising gaze policy |

Three structural **closures** anchor the framework and must be preserved by any
refactor:

- **Scaling closure** — disparity is dimensionless until L4 supplies the metric
  scale from rig geometry and vergence state. No module below L4 may return
  metres.
- **Control-regime closure** — L5 consumes L3/L4 estimates *with their
  uncertainty* and returns a command; it never re-derives depth itself.
- **Reference-frame closure** — every quantity carries an explicit frame. See §3.

## 2. Repository contract

- `src/activestereo/` is **library code only**. No scripts, no `if __name__ ==
  "__main__"`, no hardcoded paths, no plotting side effects at import time.
- `experiments/` is **experiment code only**. Each experiment is a directory
  containing `config.yaml`, `run.py`, and `findings.md`. Experiments import from
  `src`; `src` never imports from `experiments`.
- `scripts/` holds CLI entry points and Blender render scripts.
- `results/` is git-ignored. Every artefact is addressed by a run-id.
- `data/` holds pointers (DVC / git-lfs), never blobs. **Never write to `data/`.**
- `paper/` is synced with Overleaf via its Git bridge. Edit `.tex` freely;
  never rewrite `paper/refs.bib` wholesale.
- `docs/decisions/` is **append-only**. Superseding an ADR means writing a new
  one that references it, never editing the old one.

## 3. Invariants (violating these is a bug, even if tests pass)

**Units and frames.** Every array that leaves a public function is documented with
its unit and frame. The canonical set:

- Disparity: **pixels**, signed, left-image convention, positive = crossed (nearer
  than fixation).
- Depth `Z`: **metres**, cyclopean frame, `+Z` forward.
- Angles: **radians** internally. Degrees appear only at I/O boundaries.
- Vergence angle: **radians**, total angle subtended at the fixation point.
- Image coordinates: `(row, col)` for arrays, origin top-left. Never `(x, y)`
  without saying so.

**Invalid data.** Invalid or occluded pixels are represented by `np.nan`, never
by `0`, `-1`, or a sentinel float. Any operation that spatially mixes pixels
(blur, filter, downsample) **must mask invalid pixels before mixing**. See
ADR-0002 — this rule exists because violating it caused a real failure.

**Determinism.** Every stochastic component takes an explicit
`rng: np.random.Generator`. There are no calls to the global `np.random` state in
`src/`.

**Uncertainty is first-class.** Estimators return an estimate *and* its variance.
Do not add an estimator that returns a bare point estimate.

## 4. Working agreement with Claude

### Always

- **Plan before acting.** Any task touching more than one module, or more than
  ~50 lines, gets a written plan I approve first. Use Plan mode.
- **Work on a branch.** `feat/…`, `fix/…`, `exp/…`, `docs/…`. Never commit to
  `main`.
- **Run `pytest` before proposing a change is complete.** A change is not done
  because the code looks right; it is done because the suite is green.
- **Pin the finding.** When an experiment produces a result, write it to that
  experiment's `findings.md` with the run-id and git SHA.
- **Turn lessons into tests.** If we discover a failure mode, the fix ships with
  a regression test in `tests/regression/` that would have caught it.
- **Ask when the spec is ambiguous.** A wrong assumption cheaply corrected now is
  far better than a plausible-looking result I trust for a month.

### Never

- Never commit or push without me asking. Never merge a PR.
- Never `git push --force`, rewrite history, or amend a pushed commit.
- Never write to `data/` or delete anything in `results/`.
- Never add a dependency without asking. Justify it against what NumPy already does.
- Never edit `docs/decisions/*.md` that already exist.
- Never weaken, skip, `xfail`, or delete a failing test to make the suite pass.
  A failing test is information. Report it.
- Never change numerical tolerances in tests to make them pass.
- Never introduce a second convention for units or frames "just here".

### Definition of done

A task is complete when: tests pass · new behaviour has a test · docstrings state
units and frames · the ADR or lab-notebook entry is written if a decision was made
· the diff contains nothing I did not ask for.

## 5. How to work with me

I am a researcher at VISGRAF/IMPA. Engage as a peer: if a derivation is wrong or
an approach is a dead end, say so directly and explain why. I would rather be
contradicted with a reason than agreed with politely. Precision over hedging.

When you are uncertain about a numerical result, say you are uncertain and
propose the check that would resolve it.

## 6. Common commands

```bash
pytest -q                        # full suite
pytest tests/unit -q             # fast path
pytest -m slow                   # slow / render tests
ruff check src tests             # lint
ruff format src tests            # format
mypy src                         # types
python -m experiments.exp001_matcher_baseline.run --config configs/default.yaml
latexmk -pdf -cd paper/main.tex  # build the paper
```

## 7. Reading order for a fresh session

1. This file.
2. `docs/decisions/` — the accumulated "why", especially ADR-0001..0003.
3. `docs/architecture.md` — how the six layers connect.
4. The module you are about to touch, and its tests.

Do not read the whole repository into context. Ask for the files you need.
