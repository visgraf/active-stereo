# 2026-08-20 — Multi-scale energy: the rescue worked, the variance didn't

Branch `exp/multiscale-energy` (off `exp/energy-decoder`). Issue #13 filed with
falsifiers — V0 leading — before the encoder existed; findings in
`experiments/exp006_multiscale_energy/findings.md`. Runs
`exp006a-20260820T233759-4ea8400` (Stage A, commit `b764fef`) and
`exp006b-20260821T001427-fc34275` (Stage B, commit `fc34275`).

## What I expected

That coarse scales would suppress exp005's noise-won contamination class and
lift the decoder clearly off the chance floor on photographs (V0), making H2 —
does profile variance escape the anti-calibration? — testable for the first
time. I genuinely did not know which way H2 would go; the whole reason for V0
was that exp005 could not ask the question.

## What happened

**V0 passed with a 5.8× margin**: median held-out error 0.72 px against chance
floors of 19–65 px (3.5% of floor; exp005 was at 91–96%). The mechanism did
what the in-vitro test said it would — the periodic-texture unit test showed a
single fine scale aliasing (>15% gross) and the population resolving it (<5%)
before Stage A ran, Stage A's grid showed the margin monotone in scale count,
and Stage B confirmed on held-out scenes. RDS: 0.0074 px, now 10× *better*
than block where exp005 was 14× worse. H3a: error multiplier 1.0 to 1e-12
across the gain sweep — the per-scale ratio normalisation, visible end-to-end
in a regime where it finally means something. H3b: ×1.044 under exposure
change, vs block's ×44 in exp004.

**H2 falsified — validly.** Hallucination 0.914; high-contrast
occluded/matched variance ratio 0.254 (median of per-scene ratios, < 1.0 in
7/8 scenes, 0.087 at worst). Low-contrast occlusions stay safe (1.28).

## What I concluded

The three exp005 verdicts I most wanted reversed, reversed. The one hypothesis
the profile readout was *built* to test came back negative, and negative in a
way that generalises: SSD curvature (exp004), SGBM, and a population second
moment now all show the same asymmetric signature — sharp, confident,
**wrong** at high-contrast half-occlusions; honestly vague at low-contrast
ones. Three readouts agreeing relocates the defect from readout to evidence:
at a half-occlusion the matching evidence really is sharp, it just belongs to
the occluding surface. No confidence statistic computed from the left-referenced
evidence alone can see this. Escaping it needs information the profile does not
carry — left-right consistency (issue #7) or an explicit occlusion model.
That is an L3 obligation now, with three experiments of evidence behind it.

A second conclusion, about method: **the validity precondition earned its
place on the first outing.** The H2 falsifier text is identical to exp005's;
the only thing that changed is that V0 certifies the regime. Same words,
uninterpretable verdict then, citable verdict now.

## Costs and residue

- Hallucination *rose* (0.80 → 0.91): the 48 px-period scale that suppresses
  noise also pools support from inside the occluder. The V0 fix and the H2
  failure are the same mechanism seen from two sides — worth saying in the
  paper.
- Vintage is still unsolved (31.7 px, 0.49× floor) — the corpus's hard scene
  for every matcher we have run.
- Peak RSS 7.24 GB despite the argmax fix (allocator retention across five
  encodes × three variants). Fine at experiment scale.
- `im1L` (moved light source) costs ×5.6 — gain invariance is not photometric
  invariance, and nothing here claims otherwise.

## State

201 tests passing (8 new for the encoder), ruff and mypy clean. Commits
`b764fef` (encoder + decoder argmax fix + Stage A), `fc34275` (gate unlock),
findings commit to follow. Not pushed, not merged. The gate sequence — grid
table and computed selection on #13 before any held-out read — held for the
third experiment running.
