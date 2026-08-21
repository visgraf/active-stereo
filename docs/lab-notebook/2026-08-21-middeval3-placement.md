# 2026-08-21 — MiddEval3: placed on the field's ruler, and beaten by 2005

Branch `exp/middeval3`. Issue #18 filed with expectations E1–E4 before the
first evaluation of our results; findings in
`experiments/exp007_middeval3_training/findings.md`. Run
`exp007-20260821T230639-65476a0`. Scored by the benchmark's own SDK evaluator
(built locally; needed a brew `libpng`), never by our metrics module, with the
benchmark's precomputed SGM/Census results re-scored on the identical local
ruler as anchors. Training set only — the once-per-method public test
submission was deliberately not spent.

## What I expected

That block would land 30–45% dense bad2.0 (E1), that the strict threshold
would charge energy's gross-outlier tail and put it below block (E2), that the
gain-invariance argument would finally pay off on MotorcycleE/PianoL (E3), and
that energy would show the larger refusal gap (E4).

## What happened

E3 held decisively; the other three failed, each instructively.

Placement (dense, t=0.5 ≈ official bad2.0, local ruler): SOTA ~5–7 · SGM 24.2
· Census 28.9 · **ASsgbm 33.7** · **ASnrg 52.9** · **ASblk 58.0**.

- **E1 failed (58.0%)** because the expectation converted thresholds wrongly:
  exp004's bad-2.0 was 2 px at downsample 3 ≈ official bad-6.0, while
  official bad2.0 is 0.5 px at Q — a 4× stricter bar. The prediction was
  miscalibrated, not the matcher changed.
- **E2 failed the interesting way**: energy *beat* block overall (52.9 vs
  58.0), and on the 13 matched-photometry pairs they tied (53.8 vs 53.4). At
  0.5 px, block's near-threshold scatter is charged as heavily as energy's
  tails. The whole aggregate gap is the two photometric pairs.
- **E3 held**: MotorcycleE 36.9 (energy) vs 89.2 (block); PianoL 58.0 vs
  86.9. Energy's MotorcycleE score equals its Motorcycle score — literally no
  degradation under the exposure change, on benchmark-designated pairs.
  Even the benchmark's own SGM drops points there; nothing else measured
  holds flat.
- **E4 failed as stated** (12.4% vs 16.6% refusals): the direction holds on
  matched-photometry pairs but block's refusals explode on E/L pairs and
  invert the aggregate. An expectation written from a corpus with no
  photometric variation inside the scored set.

## What I concluded

We are a factor ~8–10 from the state of the art and ~2 from classic SGM, and
that is fine — these are reference implementations and a two-experiment-old
pathway, and the point was an external ruler. Three things go on the record:
sub-pixel precision, not gross failure, is the binding constraint at official
thresholds (both our L3-free matchers sit at ~43% bad among *answered* pixels
at 0.5 px); photometric robustness is the energy pathway's one
leaderboard-visible virtue; and the benchmark cannot see uncertainty at all —
a calibrated refusal and a confident fabrication are the same bad pixel in the
dense table, which is precisely why the project's variance results needed
their own experiments rather than a leaderboard.

Not promoted to an ADR: no decision was taken beyond "don't spend the test
submission yet", which findings.md records with the reasoning.

## State

Repo: exp007 experiment + `MiddEval3Scene` loader + `write_pfm` +
`fetch_middeval3.py`; 206 tests green, ruff/mypy clean. The MiddEval3 tree
(with our disp0AS*/timeAS* files in place) lives outside the repository at
`~/datasets/middeval3`.
