# Method note 004 — A reduction that annihilates reproducibility, and the direction that needed an audit

- **Series:** practice notes on AI-assisted research methodology (see
  [001](001-enforcement-and-disclosure.md), [002](002-state-across-surfaces.md),
  [003](003-premature-reduction.md)).
- **Date:** 2026-08-25
- **Provenance:** the migration step 5 session (PR #37, merged as `629ea0e`).
  Specifics, harnesses and figures live in
  [the step-5 lab-notebook entry](../lab-notebook/2026-08-25-step-5-target-to-fixation.md)
  §7; this note generalises and cites rather than restating, the relation
  ADR-0016 has to its own companion entry.
- **Numbering:** this note takes no Finding number. See *Numbering* below —
  the series has a collision, and adding to it would deepen it.

## The reduction 003's ledger lacks: reproducibility

003's ledger records reductions that annihilate sign, location, common mode, eye
index, and mechanism. Add one:

> **`max` over a random point cloud annihilates reproducibility.**

Unlike every row in that ledger, this destroys nothing about the physics. The
number is *correct* for the sample it was computed on. What it destroys is
whether a second analyst can obtain it — and that is not a lesser property, since
a figure nobody else can reproduce cannot be checked, which is the whole basis on
which numbers are trusted here.

The episode: a residual was quantified as `max |d_v|` over a random point cloud.
Two analyst choices went unstated — the seed and the sample size — and between
them they moved the figure **2.4×**. The maxima were driven by grazing samples no
camera images; the extent-fixed replacement was roughly a third of them.

It is worth stating as its own row because it is **003's second row (`max`) in a
different domain**. Over a deterministic sweep, `max` annihilates *location*.
Over a random sample, it annihilates location *and* reproducibility. So "what
does this reduction annihilate" has an answer that depends on what the reduction
is applied to, not only on which reduction it is — a sharper form of 003's check
than 003 states, and the reason the ledger is a list of cases rather than a table
of operators.

## The detection mechanism 003 lacks

> **A statistic two independent harnesses compute differently is ill-posed until
> proven otherwise. Ask what the analyst chose; do not reconcile the numbers.**

003 closes "why this one does not become a test" by saying what *can* reach
premature reduction: review by a surface with a **different** characteristic
failure. This case had no such surface. Both surfaces computed the *same*
ill-posed statistic, from the same misunderstanding of what made it well-posed.
It was caught anyway — because a shared ill-posed statistic yields **divergent
numbers** rather than one plausible one, and the divergence is visible without
anyone diagnosing its cause.

That is a second detection route, and it is cheaper than the first: it requires
no asymmetry between the surfaces, only that both compute and both report. The
instinct it rewards is the counter-intuitive one — when two numbers disagree, the
useful move is to ask what each analyst chose, not to reconcile them. Reconciling
produces a number; asking produces the discovery that the statistic was never
well-defined.

It fired twice. The second time was on **its own replacement**: an image-sampled
statistic proposed explicitly as the cure for an unstated analyst choice still
contained one, because `StereoRig` carries no image dimensions and the extent
therefore could not be fixed by the rig (issue #40). A cure for a class of defect
is not immune to that class.

## The asymmetry, which is the argument — and why it is not a tally

Three numeric disagreements arose in the step-5 thread. Sorted by **direction**:

- **two originated in Chat** and were caught because Code reported the
  disagreement rather than adopting the number. That is Chat → Code, the
  direction CLAUDE.md §5 already governs, firing unprompted with nobody looking
  for it.
- **one originated in Code** and was ratified by Chat, and surfaced only when an
  **audit was explicitly requested**. That is Code → Chat, which §5 did not
  cover. Both surfaces had already agreed, so there was no disagreement to
  notice.

**This is not the tally 003 warns against.** 003's warning is specific: counting
the two catch-columns turns the ledger into an argument for trusting one surface
more, which that episode refutes. This is a different claim, about **mechanism** —
disagreement does the work by itself; agreement does not — and it argues for a
**rule**, not a ranking. Neither surface is better staffed. One direction is
better *covered*.

That is the whole case for amending §5. A failure mode that surfaces only when
someone thinks to ask for an audit is precisely the one a rule has to carry,
because the asking is the part that was missing and rules are what supply it. A
rule that demonstrably works, set against an absence that demonstrably does not,
is stronger evidence than any count of occasions could be.

## The self-instance

003's sharpest instance was its own false premise. This note's is one level in.

The first draft of the paragraph **sorting these three cases by direction** — the
paragraph immediately above — collapsed all three into a single direction. The
grouping was by surface resemblance: all three were numbers that two surfaces
computed differently. What it annihilated was **direction**, which is the only
property that makes the category an argument for amending §5 at all. Written,
unnoticed, inside the section documenting the mechanism, and caught in review
rather than in writing.

Two smaller instances of the same shape landed in the same session and are worth
naming, because together they suggest the class is *edit-induced* rather than
authorship-induced: a paragraph whose opening referent was made false by a
paragraph inserted in front of it, and a migration-plan sub-block that contradicted
another block edited in the same commit. In all three cases the original text was
correct when written and was invalidated from a distance.

## Answers to 003's three watch-items

**(a) Whether a Code → Chat direction belongs in CLAUDE.md §5 — decided: yes, and
asymmetrically.** It is in §5 as of this note. The shape matters more than the
decision: a mirror of the forward rule would be unenforceable. The forward rule
works because the *receiver* holds the files and can check; Chat holds excerpts by
construction and cannot, so "Chat verifies Code's numbers" would rot into a
formality. §5 therefore splits it into obligations each surface can actually meet
— **disclosure** on Code (name a derived number's inputs; mark which were measured
and which assumed), **non-ratification** on Chat (a number from Code may be adopted
as a finding, but not used to settle a disagreement or retire a standing claim
without asking what it was measured against). The worked failure of each is the
same episode: an operating point derived from an assumed per-pixel variance that
was never measured, and a standing claim withdrawn on its strength.

**(b) Whether "what does this reduction annihilate" survives a case where the
reduction is RIGHT — no answer. This thread did not produce one.** The question
fired several times and cost nothing each time, which is *not* the same as having
survived a case where it should have cost something. One check that only ever
fires is still not yet a check, and 003 said so first. Recording "no case arose"
rather than furnishing one is the point: 003's own lesson is what happens when a
category gets filled by resemblance, and manufacturing an answer here would be
that error committed inside the note documenting it. **Still open.**

**(c) A third instance, and whether it arrives in analysis or library code —
answered, and it is library code.** **Rectification annihilates vertical
disparity.** ADR-0013:103-107 declares vertical disparity a *cue* — "under
rotation it is real, grows with eccentricity and vergence, and is a candidate L4
input for viewing distance" — while ADR-0013:93-97 has L2/L3 consume the
**rectified** pair, in which `d_v` is identically zero. Step 5 measured that as
`0.000e+00` over 75 gaze configurations: exactly zero, not small. A reduction
applied before the measurement, annihilating precisely the quantity that had just
been declared valuable.

This is the first instance in library code rather than analysis, and it is
**open, not closed**. It is ADR-0013's declared rectification fork — whether L3
matches on the raw pair instead — and it is step 6's preamble question, not a
finding to be filed away. Noting it here is a pointer, not a resolution.

## Numbering

This note takes **no Finding number**, because the series already collides.

Verified from git history rather than inferred. 001 was created (`35bc101`,
08-23) holding Findings 1-2. 002 then continued the series **correctly** at 3-4
(`670f759`, 08-23). 001 subsequently *grew*: Finding 3 (`d4d389d`) and Finding 4
(`b379948`) on 08-23, Finding 5 (`5d1908a`) on 08-25. 003 had meanwhile taken
Finding 5 (`4b46bb0`, 08-25).

So bare "Finding 3", "Finding 4" and "Finding 5" are each ambiguous between two
notes, and `002:20` carries a bare cross-note "Finding 2" meaning 001's. Nobody
mis-numbered anything: **001 is an append-target that kept taking numbers later
notes had already claimed.** That is the same defect class as the rest of this
note — a later edit silently invalidating statements made elsewhere — arriving in
the series' own bookkeeping.

Two conventions follow, the first of which merely ratifies existing practice:

- **Cross-note references are note-qualified** — "003's Finding 5", never bare.
  `docs/workflow.md` and the step-5 entry already write them this way.
- **A published note stops taking new Finding numbers.** A new finding goes in a
  new note. This removes the cause rather than the symptom.

Whether 001-003 are renumbered to clear the existing ambiguity is left open: it
would rewrite dated notes after the fact and break cross-references in
`docs/workflow.md`, inside 002 itself, and in the step-5 entry. The conventions
above stop it recurring either way.

## What the next notes should watch for

- Whether the **non-ratification** obligation is one Chat can actually keep, or
  whether it degrades into a ritual question with a ritual answer. It is the
  weaker half of the amendment by construction, since nothing enforces it.
- Whether **disclosure** on Code changes anything on its own. Marking inputs
  measured-or-assumed is cheap, and cheap obligations are the ones that get
  performed rather than done.
- Whether the ill-posed-statistic check ever fires on a statistic that turns out
  to be **well**-posed, with the two harnesses simply differing by a bug. The
  check says "ill-posed until proven otherwise"; the cost of that default has not
  been paid yet.
- The rectification fork (item **c** above) reaching step 6, and whether the
  vertical-disparity cue survives the pipeline that consumes the rectified pair.
