# Working methodology

## Roles

| Surface | Use it for |
|---|---|
| **Claude Code (VS Code)** | Implementation, refactoring, tests, experiment runners, debugging |
| **Claude chat** | Derivations, framework design, literature positioning — anywhere you want an interlocutor, not an agent |
| **GitHub** | Experiment ledger (Issues), review gate (PRs), reproducibility (Actions) |
| **Overleaf** | Co-author editing surface for `paper/`, synced via the Git bridge |
| **Cowork** | Later: literature sweeps, turning `results/` into decks and reports |

### Starting a Chat session

Claude Code reads [`CLAUDE.md`](../CLAUDE.md) automatically at the start of
every session. **Chat has no equivalent — it starts with nothing.** So the
opening brief has been carried in the maintainer's habit, which is the failure
mode CLAUDE.md §5 names: knowledge that lives only in one surface's session is,
as far as the project is concerned, knowledge the project does not have. This
section is that brief, written down.

**Read current state; do not recall it.** Open the repo and read, rather than
reasoning from a remembered snapshot. The cost is not hypothetical: method note
[002](method/002-state-across-surfaces.md), Finding 3, records an amendment
drafted against a stale merge status and *silently lost to a merge* between
drafting and delivery. Nothing failed loudly — a piece of work simply became
impossible.

Reading list, in order:

1. [`docs/roadmap.md`](roadmap.md) — the Phase A–E arc and current intent.
   Strategic, authored by the maintainer; treat revisions there as
   instructions, not hypotheses.
2. [`docs/workflow.md`](workflow.md) — this file: roles, the loop, the autonomy
   ladder.
3. [`CLAUDE.md`](../CLAUDE.md) — the constitution. §3's invariants and §4's
   working agreement bind *prompts* as much as they bind Code.
4. [`docs/decisions/README.md`](decisions/README.md) — the ADR index, including
   which are superseded or corrected. Read the ADRs a task touches, not all of
   them.

**Role boundary.** Chat does derivation, adversarial review, and prompts for
Code. Not repo code, not implementation detail. Method note
[001](method/001-enforcement-and-disclosure.md)'s Finding 2 is blunt about why:
the surface holding the files beats the surface holding excerpts, two for two.
A Chat-authored implementation is a hypothesis at best, and reviewing Code's
reasoning is worth more than competing with its file access.

**The handoff contract, Chat side.** CLAUDE.md §5 states the Code side — what
Code must do with claims arriving from Chat. This is the obligation that
creates:

- **Numeric claims are hypotheses with `file:line` pointers, never values.**
  Assert *where to check*, not *what the number is*. A wrong pointer costs one
  verification; a wrong value can reach an ADR, and ADRs are append-only.
- **State the repo state the prompt assumes** — branch, HEAD SHA, merge status
  of anything in flight — so Code can verify it and *reject a stale prompt*
  rather than execute it against a repo it no longer describes.
- **Invite the contradiction.** A prompt that says "verify, do not adopt" gets
  a better answer than one that asserts. Every numeric error caught so far was
  caught because it was flagged as unverified rather than stated as fact.

*Status note:* 002's Finding 3 proposed the repo-state rule for CLAUDE.md §5 and
recorded it as "not yet applied". Writing it here makes it normative in the
workflow while the constitution still does not carry it. Whether it graduates to
CLAUDE.md §5 is a maintainer decision, not a documentation one.

**Norms that bind prompts, not just Code.** Pointers rather than a restatement,
so this cannot drift out of sync with the constitution: ADRs are append-only and
hook-enforced (§4, and `docs/decisions/README.md` on how); plan mode before
anything substantial (§4); units and frames are not negotiable per-prompt (§3);
and a deny rule is a statement about which decisions Code does not make
unilaterally, not an obstacle to route around (§4) — so a prompt should never
ask for the equivalent path.

**The bootstrap this cannot solve.** A note telling Chat what to read only helps
if Chat is told to read it, and nothing in Chat enforces that. What it changes
is the size of the thing the maintainer has to remember: one link to this
section, instead of the norms reconstructed from memory each time.

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
