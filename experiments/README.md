# Experiments

One directory per experiment: `expNNN_short_name/`, containing

- `config.yaml`   — the exact configuration, composed from `configs/`
- `run.py`        — the runner; imports from `src`, writes to a `RunContext` dir
- `findings.md`   — what happened, pinned to run-ids and SHAs

Experiments import from `src`. **`src` never imports from `experiments`.**

Before writing `run.py`, open a GitHub issue stating the hypothesis and the
acceptance criteria. If you cannot say what result would falsify the hypothesis,
the experiment is not ready.
