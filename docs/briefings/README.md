# Briefings

One per experiment that produced a result worth explaining to someone who was not
in the room. A briefing is the *intuitive* account: what we asked, what we
expected, what happened, and what it changes.

It is not a replacement for the experiment's `findings.md`, which stays the
record of record — pinned to a run-id and a git SHA, with the falsifiers as
stated beforehand. The briefing is what you would say out loud.

If the two ever disagree, `findings.md` is right and the briefing is stale.

## Cross-experiment syntheses

A briefing may also cover several experiments at once, where the interesting claim
is one no single experiment can make. A synthesis has **no hypotheses and no
falsifiers** — it did not register any — so it must say so at the top and label any
new observation as exploratory, needing its own pre-registered test before it
counts as a result. It is still bound by the rule above: where it touches an
experiment's numbers, that experiment's `findings.md` wins.

| | |
|---|---|
| [exp003](exp003-appearance-and-matching.md) | when a matcher knows that it doesn't know |
| [exp004](exp004-real-data-transfer.md) | the same question on real photographs |
| [synthetic → rendered → real](synthetic-to-rendered-to-real.md) | synthesis across exp001, exp003 and exp004 |
