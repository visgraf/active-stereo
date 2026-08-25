# active-stereo

A six-layer framework modelling **stereoscopic 3D vision as active Bayesian
inference**, spanning generative geometry, neural encoding, disparity-field
inference, metric scaling and cue fusion, oculomotor control, and an
active-sampling outer loop.

VISGRAF Laboratory, IMPA.

---

## Quick start

```bash
git clone <this-repo> && cd active-stereo
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,cv,viz]"
pytest -q
astereo info
```
Run the end-to-end demo (the successor to `active_stereo_demo.py`):

```bash
python scripts/demo_active_stereo.py --scene disk --matcher sgbm --plot
```

Run the first experiment:

```bash
python -m experiments.exp001_matcher_baseline.run \
    --config experiments/exp001_matcher_baseline/config.yaml
```

## Layout

```
src/activestereo/   library code only — the six layers, scenes, io, viz, utils
experiments/        one directory per experiment: config, runner, findings
tests/              unit/ (contracts) and regression/ (ADR-backed lessons)
configs/            composable YAML; every run fully specified
scripts/            CLI entry points and Blender render scripts
data/               DVC / git-lfs pointers — never blobs
results/            git-ignored, addressed by run-id
paper/              LaTeX, synced with Overleaf via its Git bridge
docs/               architecture, workflow, decisions/ (ADRs), lab-notebook/
```

`src/` holds no scripts. `experiments/` holds no library code. That single rule
is what keeps a research repo from collapsing into a pile of one-off files.

## The six layers

| | Package | Concern |
|---|---|---|
| L1 | `geometry` | Generative geometry, Vieth–Müller horopter |
| L2 | `encoding` | Binocular energy model, disparity tuning |
| L3 | `inference` | Disparity-field inference: matchers, MRF/BP |
| L4 | `scaling` | Metric scaling, MLE cue fusion |
| L5 | `control` | Vergence estimation, Kalman filtering, stability |
| L6 | `policy` | Saliency, foveal confinement, gaze policy |
| — | `scenes` | Stimuli: random-dot stereograms, rendered scenes (ADR-0006) |

See [`docs/architecture.md`](docs/architecture.md).

## Invariants

Four rules the whole codebase depends on. Violating one is a bug even when the
tests pass.

- **Units and frames are explicit.** Disparity in pixels (left-image convention,
  positive = crossed); depth in metres, cyclopean frame; angles in radians
  internally.
- **Invalid is `nan`**, never `0` or `-1`. Any operation that spatially mixes
  pixels masks validity first ([ADR-0002](docs/decisions/0002-saliency-validity-masking.md)).
- **Uncertainty is first-class.** Estimators return `Estimate(value, variance)`
  ([ADR-0005](docs/decisions/0005-uncertainty-first-class.md)).
- **Determinism.** Stochastic components take an injected `np.random.Generator`.

Full statement in [`CLAUDE.md`](CLAUDE.md) §3.

## Decisions

`docs/decisions/` is append-only. Three of the seed ADRs record lessons already
paid for in the prototype, and each has a regression test that would have caught
the original failure:

- [ADR-0001](docs/decisions/0001-windowed-median-vergence.md) — windowed-median
  vergence, not single-pixel
- [ADR-0002](docs/decisions/0002-saliency-validity-masking.md) — mask validity
  before any spatial mixing
- [ADR-0003](docs/decisions/0003-foveal-confinement-linearization-error.md) —
  foveal confinement via the linearisation remainder

## Working with Claude Code

[`CLAUDE.md`](CLAUDE.md) is the project constitution, read automatically at the
start of every session. [`docs/workflow.md`](docs/workflow.md) describes the
surface roles, how to start a Chat session, and the autonomy ladder. Four custom
commands live in `.claude/commands/`:

| Command | Use |
|---|---|
| `/plan-experiment` | Draft a falsifiable plan before any code |
| `/adr` | Draft an ADR for a decision just made |
| `/regress` | Turn a bug into a permanent regression test |
| `/check-invariants` | Audit a diff against §3 and the closures |

## Status

108 tests green. Migration from the prototype is in progress — `encoding` now
has a `GaborEnergyEncoder` (see [exp002](experiments/exp002_energy_model_validation/findings.md):
gain invariance validated, per-pixel precision under investigation), and
`inference` still awaits MRF belief propagation.

Stimuli now span both families ADR-0006 argues for: random-dot stereograms, and
appearance-controlled Blender renders spanning dense texture to constant albedo
([exp003](experiments/exp003_appearance_and_matching/findings.md)).

Three open modelling questions are tracked rather than hidden: L1 models a
shifted-frustum rig, not the Vieth–Müller horopter it claims
([ADR-0007](docs/decisions/0007-offaxis-not-toein.md)); SGBM's variance is a
constant rather than a posterior width, which makes cross-matcher fusion
comparisons unfair; and L3 reports texture loss honestly (637× variance
inflation) but half-occlusion not at all (5×), so fabricated matches still reach
L4 at close to full weight. See [`docs/lab-notebook/`](docs/lab-notebook/).