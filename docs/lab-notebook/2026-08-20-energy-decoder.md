# 2026-08-20 — EnergyDecoder: L2→L3 closed, and what it cost to find out

Branch `exp/energy-decoder`. Issue #12 filed with falsifiers before the decoder
existed; findings in `experiments/exp005_energy_decoder/findings.md`.

## What was built

`inference.EnergyDecoder` — the first consumer of an L2 response volume in the
pipeline. Profile readout: baseline subtraction, ratio-based flatness refusal,
local centroid, full-profile second moment + step²/12. The refusal rule was
refined from #12's absolute-floor sketch to a ratio *before any run*, because an
absolute floor makes the refusal decision gain-dependent while value and
variance are not; the unit suite pins bit-exact invariance of all three for
power-of-two gains.

## The gate held, and mattered

Stage A (RDS only) → constants + numbers posted to #12
(`issuecomment-5363078374`) → `stage_b_unlocked` flipped in the same breath
(`83d48ab`) → only then Middlebury. The runner enforces the lock itself, because
this project has already had two undeclared peeks.

The Stage A comment recorded, explicitly as prediction: decoder variance ratio
already 0.957 in RDS occlusions (block: 1.923). Stage B confirmed the direction
(0.903 on photographs). On the record as foresight, not hindsight — that is what
the gate is for.

## The test that failed before anything ran

The promised centre-bias unit test failed on first execution: +1 px pull on a
33-channel bank, +3 px on 65. Diagnosis took three sweeps: it scales with
distance from the bank *centre* (not the edge), a ±2-channel centroid cannot
move a value 3 px, and neither readout constant touches it. It is
**contamination** — answered pixels are a mixture of peak-won (unbiased,
+0.006 px) and noise-won (argmax uniform over the bank). The test was rewritten
to pin what is true (conditional unbiasedness) and to pin the contamination as a
characterised regression, with the diagnosis in its docstring.

## Results, in one breath

H1a falsified 14× over its bar. H1b falsified below the raw-argmax bar — the
centroid converts forgiving discrete bins into unforgiving continuous spread;
evidence against issue #1's option (a). H2 falsified on its letter in all eight
held-out scenes. H3 survived by two orders of magnitude and **means nothing**:
the decoder's Middlebury errors are at 91–96% of the uniform-guess floor, and
chance cannot be photometrically degraded.

## Two lessons worth more than the verdicts

**Falsifiers need validity preconditions.** H3 is the third instance of the same
design flaw (after exp004's vacuous SGBM cells): a threshold stated without
asking whether the estimator is in a regime where the threshold can bind. The
check that caught it — compare the baseline to an explicit chance floor before
interpreting any survivor — took four lines and should be standard.

**A component validated in isolation can be at chance in the system.** exp002
measured the encoder near-exact on its own passband (0.031 px gain drift);
end-to-end on photographs the same encoder is indistinguishable from guessing.
Neither result is wrong. The passband (σ=6, ~24 px period) simply does not
overlap the structure real images put through it at this resolution. Component
validation bounds what a part *can* do, not what the system *does* do.

## State

195 tests passing, ruff and mypy clean. Commits `f86c594` (decoder + Stage A),
`83d48ab` (gate unlock), findings commit to follow. Not pushed, not merged.

Next step if wanted, deliberately not taken here: a multi-scale bank, with its
own issue, falsifiers, and — this time — validity preconditions on every one.
