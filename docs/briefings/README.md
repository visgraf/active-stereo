# Briefings

The *intuitive* layer over the repository: what we asked, what we expected, what
happened, and what it changes — written for someone who was not in the room.

A briefing is **not** a replacement for an experiment's `findings.md`, which stays
the record of record: pinned to a run-id and a git SHA, with the falsifiers as
stated beforehand. The briefing is what you would say out loud.

**If the two ever disagree, `findings.md` is right and the briefing is stale.**

## Start here

| | |
|---|---|
| [**The architecture**](architecture.md) | six layers, three closures, and an honest map of what is actually wired |

Read that first. Every experiment below is a claim about one part of it, and the
through-line — that the interesting failures in this project have all been
failures of *uncertainty* rather than of accuracy — only makes sense against the
structure that made uncertainty first-class.

## One per experiment

| | | concepts it also covers |
|---|---|---|
| [exp001](exp001-matchers-and-the-baseline.md) | why "how often is it right?" was the wrong question | what a matcher is · block matching vs SGBM · declining as a legal answer |
| [exp002](exp002-energy-models.md) | the half of the energy model that survived | quadrature energy models · why L2 produces evidence, not decisions |
| [exp003](exp003-appearance-and-matching.md) | when a matcher knows that it doesn't know | texture, gloss and lighting as controlled variables |
| [exp004](exp004-real-data-transfer.md) | the same question, on real photographs | measured ground truth and what it costs |
| [exp005 + exp006](exp005-exp006-energy-pathway.md) | the energy pathway: from island to layer, and what its confidence is worth | population readouts · coarse-to-fine multi-scale banks · validity preconditions on falsifiers |

## Cross-experiment syntheses

A briefing may also cover several experiments at once, where the interesting claim
is one no single experiment can make. A synthesis has **no hypotheses and no
falsifiers** — it did not register any — so it must say so at the top and label any
new observation as exploratory, needing its own pre-registered test before it
counts as a result. It is still bound by the rule above: where it touches an
experiment's numbers, that experiment's `findings.md` wins.

| | |
|---|---|
| [synthetic → rendered → real](synthetic-to-rendered-to-real.md) | what transferred across exp001, exp003 and exp004, and what was an artefact of the stimuli — with a postscript from the energy pathway's crossing |

## A note on experiments whose stories changed after they were written

Two of these briefings were revised by later work, and each carries the revision
inline — dated, beside the original text — rather than by rewriting history:

- **exp002** ended in a deliberately open decision — one falsifier failed and
  the question of what that meant was handed back rather than resolved by
  tuning. [exp005 and exp006](exp005-exp006-energy-pathway.md) answered it: a
  genuine single-scale limitation, option (c). The original sections stand as
  written, with the resolution added.
- **exp001**'s finding held on every stimulus family since; its *recommendation*
  did not survive [exp004](exp004-real-data-transfer.md), and the briefing carries
  the revision inline.

A briefing that quietly presents unfinished work as settled is the same failure as
a stale one — and so is one that quietly rewrites what it originally claimed.
