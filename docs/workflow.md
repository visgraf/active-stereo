# Working methodology

## Roles

| Surface | Use it for |
|---|---|
| **Claude Code (VS Code)** | Implementation, refactoring, tests, experiment runners, debugging |
| **Claude chat** | Derivations, framework design, literature positioning — anywhere you want an interlocutor, not an agent |
| **GitHub** | Experiment ledger (Issues), review gate (PRs), reproducibility (Actions) |
| **Overleaf** | Co-author editing surface for `paper/`, synced via the Git bridge |
| **Cowork** | Later: literature sweeps, turning `results/` into decks and reports |

## The loop

1. **Issue first.** Every experiment is an issue with a hypothesis and acceptance
   criteria written *before* work starts. If you cannot state what would falsify
   it, you are not ready to run it.
2. **Branch.** `exp/NNN-short-name`, `feat/…`, `fix/…`, `docs/…`.
3. **Plan mode.** Ask Claude for a plan before implementation. Read it. Edit it.
   Approve it. This is where most errors are cheapest to catch.
4. **Implement.** Manual approval mode by default; accept-edits once the task is
   well-specified and the tests are trustworthy.
5. **Run.** `RunContext` writes a manifest pinning the git SHA, seed, and config.
6. **Record.** Findings go in `experiments/expNNN/findings.md` with the run-id.
   A decision goes in `docs/decisions/` as an ADR.
7. **PR.** Claude opens it, you merge it. Never the reverse.

## Autonomy ladder

Increase autonomy as the test suite earns it, not as impatience demands it.

| Level | Mode | When |
|---|---|---|
| 0 | Plan mode, you approve every step | New subsystem, unfamiliar math |
| 1 | Manual — approve each edit | Default for `src/` |
| 2 | Accept edits, review the diff | Tests are green and meaningful, task well-specified |
| 3 | Accept edits + auto-run tests | Mechanical refactors, docs, plotting |

Never grant bypass permissions on this repo. There is no task here that is worth
it.

## What earns autonomy

A test suite that would *catch the mistake*. Coverage percentage is not the
metric; the metric is whether a plausible wrong implementation would fail. Every
lesson learned becomes a regression test precisely so that autonomy can grow.
