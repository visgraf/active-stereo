# Method note 002 — Stale state across surfaces, and probes that miss their target

- **Series:** practice notes on AI-assisted research methodology (see
  [001](001-enforcement-and-disclosure.md)).
- **Date:** 2026-08-23
- **Provenance:** the ADR-0014 session (branch
  `docs/adr-0014-listing-coefficient`), plus the permission verification it
  forced. Written in Claude Code; the enforcement findings below are about
  the agent writing them.

## Finding 3 — Surfaces drift out of sync on repo state, silently

Chat drafted an amendment to ADR-0013 asserting the repo state "PR #21, not
yet merged" — without checking — while three PRs were in flight. By the time
the amendment could land, #21 had merged and the ADR was append-only: the
amendment was **silently lost to a merge**. Nothing failed loudly; a piece of
work simply became impossible between drafting and delivery.

This is Chat's third factual error in one thread (two numeric, per 001's
Finding 2; now one on state), and it has a different mechanism: not
truncation of excerpts but **staleness** — a surface reasoning from a
snapshot ages out of sync with a repo that other actors are advancing.

**Contract addition, proposed for CLAUDE.md §5 (recorded here, not yet
applied):** prompts arriving from Chat must *state the repo state they
assume* — branch, HEAD SHA, merge status of in-flight PRs — so Code can
verify and **reject a stale prompt** instead of executing it against a repo
it no longer describes. The ADR-0014 prompt did exactly this ("REPO STATE
THIS ASSUMES — verify before proceeding, reject if stale"), the verification
passed, and the task proceeded on a confirmed base: the contract is already
practiced and works. It should be written down.

Note the closing of a loop: the permission fix of PR #23 is what blocks the
amendment that prompted it. That is the system working as designed — the
correction to ADR-0013 now *costs an ADR* (ADR-0014), which is exactly the
price append-only was supposed to attach.

## Finding 4 — A probe that does not match the pattern under test verifies nothing

PR #23's verification of "creating a new ADR remains possible" used the probe
file `9999-permission-probe.md` — chosen to look obviously not-an-ADR. Every
real ADR filename starts with `0`, and the deny pattern under test was
`Edit(docs/decisions/0*.md)`. The probe therefore exercised the *ask* rule
(`Write(docs/decisions/**)`) and never touched the deny pattern at all. The
conclusion "creation stays possible" was true of the probe and false of every
actual ADR — discovered only when the `Write` of `0014-…md` was denied.

Rule for future probes: **the probe must match the pattern under test**, in
every dimension the pattern discriminates on (here: the filename prefix).
A probe designed for cosmetic harmlessness can be designed out of the very
equivalence class it is supposed to represent.

Two further enforcement facts established while repairing this:

- **`Edit`-family permission rules govern `Write` too.** A deny written as
  `Edit(docs/decisions/0*.md)` blocks creating `0014-…md` via `Write`. The
  permission syntax cannot express "deny modification of existing files,
  allow creation of new ones" for the same pattern.
- **Ask-level gating is session-fragile and not auditable after the fact.**
  With the rule moved to `ask`, a controlled probe pair showed `Write`
  prompting while `Edit` on an existing ADR ran *unprompted*. No config
  source was found (`settings.local.json` absent, user settings empty); the
  leading hypothesis is a session-scoped "don't ask again" edit grant that
  the researcher could not remember issuing. That indeterminacy is itself
  the finding: **an ask rule's effective strength depends on accumulated
  session grants that leave no inspectable record.** 001's watch-item —
  prompt fatigue converting ask into allow — was observed live within one
  day of being written.

**Resolution adopted:** existing-ADR protection returned to `deny`
(verified: the probe is blocked at the permission layer, which overrides
whatever session state exists). The accepted cost, stated plainly: creating
a new ADR now requires a deliberate, researcher-made settings change
(deny → ask → deny, one toggle per new ADR) — or the `PreToolUse` hook
proposed in 001, which would gate by filename deterministically, independent
of mode and session grants. Until the hook decision is made, one settings
toggle is the ceremony a new ADR costs, and given what an ADR is, that
ceremony is arguably correct.

## What the next notes should watch for

- Whether the per-ADR settings toggle survives contact with practice or gets
  quietly left at `ask` after the next ADR — which would be prompt fatigue
  operating at the config layer rather than the click layer.
- Whether stale-state rejections (Finding 3's contract) ever fire in anger,
  and whether Chat's stated assumptions stay honest once they become
  boilerplate.
- Whether probe discipline (Finding 4) needs to become a checklist item in
  CLAUDE.md's definition of done for governance changes: *every verified
  claim names the probe and shows it matches the pattern under test.*
