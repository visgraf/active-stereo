# Method note 003 — Premature reduction, and the direction the handoff contract does not cover

- **Series:** practice notes on AI-assisted research methodology (see
  [001](001-enforcement-and-disclosure.md), [002](002-state-across-surfaces.md)).
- **Date:** 2026-08-25
- **Provenance:** the migration step 4 sessions — ADR-0016 (PR #33) and the
  toed-in projection (PR #34). Written in Claude Code. The sharpest instance
  below is a claim this note was originally commissioned to generalise, which
  turned out to be false; the note is what survived checking it.

## Finding 5 — A reduction applied before the comparison destroys the structure the comparison exists to detect

Five times in one week, a test or an estimate compared the wrong thing —
not because the physics was misunderstood, but because a **reduction** was
applied on the way to the comparison, and the reduction annihilated exactly
the property under test. The reductions were all ordinary: absolute value,
maximum, difference, a shared mask. None looked like a decision at the time.

### The ledger

| reduction | applied to | what it annihilated | how it surfaced |
|---|---|---|---|
| `\|·\|` before a ratio | the eccentricity ladder pinning `D ~ e0 + c·η²` | **sign** | `D` crosses zero at η ≈ 0.0143; the `\|·\|` ladder gives 4.22 / 4.63 / 10.08, the signed one 4.0201 / 4.0050 / 4.0013 |
| `max` before comparing | the oblique residual law | **the location of the extremum** | `max\|d_h\|` and `max\|col\|` need not fall at the same sample, so 2.2% agreement held for a reason the law does not supply |
| difference before testing | the per-eye meridian test | **common mode** | a disparity test passes whenever both eyes are wrong the same way; per-eye is not even half the differential (0.2031 vs 0.3813 px) |
| one mask for two eyes | projection validity | **the eye index** | identical to machine precision at sagittal gaze, ±1.19e-2 m vs −9.99e-3 m at az = 0.35 |
| a constant for a measurement | the peripheral-reach guard | **the measurement itself** | `np.abs(d_h[mask]).size and 160.0` evaluates to `160.0`, so the guard asserted `160.0 > 100.0` |

The last row is the degenerate limit of the pattern — reduction all the way to
a literal — and it is the one that matters most, because the reduced quantity
was a *guard against vacuous passes*, sitting in the file whose purpose was
ruling them out.

### The sharpest instance is this note's own premise

The PR #34 lab-notebook entry closed its first section with:

> This is the second time in three days that taking an absolute value destroyed
> a structural result (cf. the τ-table tolerance in the companion entry); both
> times the signed quantity was the well-behaved one.

That is false, and it merged. The companion entry, written the same day,
diagnoses the τ-table event correctly and differently: the tolerance prediction
`x·(τ_R² − τ_L²)/2` failed **by dropping ψ⁰ ≈ −az_e·el/2**, a wrong-variable
error. It contains squares, not absolute values, and the omitted term would have
been omitted from a signed formulation just the same. Two merged entries
contradicted each other about one event.

The reduction here was **collapsing two distinct failures into one category by
surface resemblance** — both involved sign or magnitude somewhere — which
annihilated the *mechanism*, the only thing that would have made the category
useful.

**Attribution, because it is the content.** Code proposed "twice this week", in
a summary of its own work. Chat ratified it and amplified it, commissioning a
method note on the strength of it. Neither checked it against the two entries,
which sat in the repo, contradicting each other, the whole time.

The mechanism is structural rather than careless. CLAUDE.md §5's handoff
contract governs **Chat → Code**: numeric claims arriving from a surface that
read excerpts are hypotheses with pointers, to be verified before anything
durable records them. Nothing governs **Code → Chat**. So a summary flowing the
other way was treated as a value rather than a hypothesis — the exact inversion
of the rule that has caught every such error so far.

001's closing section predicted this on 2026-08-23:

> Whether the handoff contract needs a reverse direction: claims flowing
> Code → Chat carry their own risk (a session summarising its own work is an
> excerpt-holder with respect to the transcript).

It happened two days later. A session summarising its own work is an
excerpt-holder with respect to its own transcript, and it is a *worse* one than
a fresh reader, because it recognises the material and therefore does not
re-read it.

### The ledger runs both ways, and splits by kind rather than volume

Chat caught: the ratio-over-`|·|`; the max-against-max law comparison; the
differential-vs-per-eye gap; the sagittal hole in the validity test; the dead
peripheral guard.

Code caught: stale repo state; the 1e-6 tolerance prediction; the unclipped
0.354 px window figure; the metric-vs-window diagnosis; that per-eye is not half
of differential; the bit-identical reimplementation criterion.

**Each surface's characteristic failure is the other's characteristic catch.**
Chat reasons from structure and mis-states magnitudes and repo state; Code
measures magnitudes and over-generalises structure. That is why the split is by
kind, not by volume — and why counting the two columns would be the same error
as this note's false premise. Tallied as an asymmetry, the ledger reads as an
argument for trusting one surface more, which this episode refutes: the surface
that would have won that argument is the one that ratified a false premise
without checking.

### The check

Not a maxim — "prefer signed quantities" would be a rule of thumb that fails the
moment a reduction is correct, which is most of the time. A question, asked at
the point of composing a comparison:

> **What does this reduction annihilate, and is it the thing I am trying to
> detect?**

`|·|` annihilates sign. `max` annihilates *where*. A difference annihilates
common mode. A shared index annihilates *which*. A category annihilates
mechanism. Each is fine unless the answer to the second half is yes.

### Why this one does not become a test

CLAUDE.md's standing rule is to turn a lesson into a regression test, and that
rule does not reach this failure — which is worth stating rather than quietly
skipping.

A regression test pins a comparison **that has already been chosen**. Premature
reduction happens while the comparison is being composed, and every instance in
the ledger above would have produced a *passing* test: the `|·|` ladder, the
max-against-max law, the differential meridian check and the single validity
mask all pass, on correct code, while measuring something other than the claim.
The dead guard passed for two commits. A test cannot catch a reduction that
happens upstream of the test's own premise.

What can reach it is review by a surface with a different characteristic
failure, which is what the ledger above records happening five times.

## What the next notes should watch for

- Whether a **Code → Chat** direction of the handoff contract is worth stating
  in CLAUDE.md §5 explicitly, now that the predicted failure has occurred once.
  The argument against is that it doubles a rule already long; the argument for
  is that the one-directional version was written *because* a claim crossed a
  surface boundary unverified, and this claim crossed the same boundary the
  other way.
- Whether "what does this reduction annihilate" survives contact with a case
  where the reduction is the right move and the question produces friction
  rather than a catch. One check that only ever fires is not yet a check.
- A third instance of the reduction pattern, and whether it arrives in analysis
  (where these five were) or in library code (where none were).
