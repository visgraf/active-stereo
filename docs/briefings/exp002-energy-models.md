# exp002 — What an energy model is, and the half of it that survived

**Record of record:** [`experiments/exp002_energy_model_validation/findings.md`](../../experiments/exp002_energy_model_validation/findings.md)
· **Issue:** [#1](https://github.com/visgraf/active-stereo/issues/1) *(still open)*
· **Run:** `exp002-20260815T200128-965a3ad`

> **This experiment ends in a question, not a conclusion.** One of its two
> falsifiers failed, and the decision about what that means was deliberately left
> to the researcher rather than resolved by adjusting parameters until the number
> turned green. That decision is still open.

---

## Why there is a layer between the images and the matcher

A matcher (L3) answers "what is the disparity here?" — it produces a **decision**.
The layer below it, L2 (`encoding/`), produces **evidence** and no decision at all:

```python
class DisparityEncoder(Protocol):
    def encode(self, left, right) -> FloatArray:  # (K, H, W), non-negative
```

For each pixel it returns a whole *profile* over K candidate disparities: how
strongly this pixel supports 8 px, how strongly 9 px, and so on. The `argmax`
belongs to L3, deliberately. Taking it inside the encoder would throw away the
shape of the profile, and the shape is where uncertainty lives — a sharp peak and
a broad plateau are different states of knowledge even when their maxima coincide.

That split is not just software hygiene. It is the framework's claim about
biology: **the visual system does not compute a disparity, it computes a
population response, and everything downstream reads that population.**

## What an energy model is

Neurons in visual cortex that are selective for disparity do not appear to
subtract the two eyes' images. The standard account — the *binocular energy model*
(Ohzawa, DeAngelis & Freeman 1990) — is that a complex cell squares and sums the
outputs of a **quadrature pair**: two filters identical except that one is shifted
a quarter-cycle relative to the other, like sine and cosine.

Squaring is what makes this different from a difference. It makes the response
depend on the *correlation structure* between the eyes rather than on their
absolute brightness — which is why the model tolerates one eye being dimmer than
the other, a thing that happens constantly in real viewing and that a
subtract-and-square matcher handles badly.

Our implementation filters each eye with a complex Gabor — a Gaussian envelope
times an oscillating carrier, the quadrature pair packed into one complex number —
and then, for each candidate disparity `d_k`:

```
E_k(x) = relu( Re( Z_L(x) · conj( Z_R(x − d_k) ) ) )
```

Read it as: *rotate the right eye's response to undo a shift of `d_k`, and ask how
well it lines up with the left eye's.* Where `d_k` equals the true disparity the
two responses are the same complex number, and their product is a maximum.

### The version that did not work, and why it is in the docstring

An earlier attempt skipped the spatial re-indexing and used a pure phase rotation:
`Z_L(x) + Z_R(x)·exp(−i·frequency·d_k)`. The reasoning — phase advances linearly
with position for a locally narrowband signal — is correct, and the approximation
breaks once the disparity being tested exceeds roughly one envelope width. At the
parameters used here it measurably failed the unit tests.

The position-shift form has no such approximation. It relies on Gabor filtering
being **linear and shift-equivariant**, so that if the true disparity is `d0` then
`Z_R(x − d0)` is *exactly* `Z_L(x)`, up to noise and edge effects. This is the
kind of thing worth keeping in a module docstring: the failed approach is the
reason the current one is written the way it is.

## The question

Migrating this encoder from an earlier prototype raised an awkward possibility.
The `DisparityEncoder` Protocol is easy to satisfy — a plain shift-and-correlate
encoder, no quadrature anywhere, would pass every conformance test and produce a
`(K, H, W)` volume that peaks in the right place on textured noise.

So conformance proves nothing about mechanism. The question was whether we had a
real energy model or something wearing its interface.

**Hypothesis:** the encoder reproduces the canonical energy-model signature — the
peak channel sits at the true disparity, and that peak is invariant to
interocular contrast gain.

Two falsifiers, both numeric, both fixed in advance:

1. **Precision.** Peak channel off `d0` by more than one bank-step for more than
   5% of valid pixels at gain 1.0.
2. **Gain invariance.** Population-mean peak drifting by more than 0.5 px across
   the gain sweep `{0.5, 0.75, 1.0, 1.25, 1.5}`, applied to the right image only.

The second one is the discriminating test. Dimming one eye is precisely what a
differencing encoder cannot absorb and a correlation-based one can.

## What happened: one decisively, one not at all

**Gain invariance survived, and it was not close.** Median drift across the full
sweep was **0.031 px**, against a 0.5 px threshold — two orders of magnitude
under, essentially at noise level, with per-seed values from 0.024 to 0.035.

It should be, and the reason is worth stating because it is exact rather than
empirical. Scaling the right image by a positive gain `g` scales `Z_R` by `g`,
because the filter is linear. That scales every `E_k` by the same `g`, because the
combination is a product. And `relu` commutes with positive scaling. So the
`argmax` is *mathematically* unchanged for any `g > 0`. The experiment did not
discover the invariance; it confirmed that the implementation has the property its
algebra says it should, which is what validation of a migration is for.

**Precision failed, and not marginally.** Only 50–58% of valid pixels landed within
one bank-step of the true disparity, against a ≥95% threshold.

But the failure has a specific shape. The population **mean** peak channel was
7.93–8.16 against a true `d0` of 8 — centred almost exactly right. So this is not
bias. Individual pixels scatter by a few px around a correct mean. It is a
**precision** problem, not an accuracy one, and those call for different fixes.

## The diagnosis — plausible, and explicitly not confirmed

The encoder pools its coherence values over a 7×7 window before reporting, on the
same reasoning as the block matcher's box-sum: average out per-pixel noise.

But the two are not doing the same thing. `BlockMatcher` pools 49 **raw pixel**
differences, which are close to 49 independent samples. This encoder pools 49
**already-Gabor-filtered** values — and the Gabor kernel has a radius of about
18 px, so adjacent windows across a 7 px pooling neighbourhood overlap almost
completely. The 49 values are heavily correlated. The same window size buys far
less noise reduction, because there is far less independence to exploit.

If that is right, a pooling window wide relative to the ~18 px kernel — or
averaging several independent stimulus draws per pixel — should tighten the
distribution without changing the mechanism at all.

**No parameter was changed to test this.** Not `window`, not `sigma`, not
`frequency`, and neither threshold. A failing result gets reported and escalated,
not quietly tuned into a pass — and a threshold adjusted after seeing the number
it failed is not a threshold.

## The decision that is still open

`findings.md` hands back three options, and the choice is a research judgement
rather than a technical one:

- **(a)** Treat the ≥95%-within-±1px criterion as an uninformed guess made at
  design time, and restate the hypothesis against the population-mean statistic —
  which is arguably the quantity the mechanism claim was ever about.
- **(b)** Widen the pooling window and rerun, testing the correlated-pooling
  diagnosis directly.
- **(c)** Accept it as a genuine limitation of a **single-frequency,
  single-scale** encoder. Real visual cortex has banks at many scales; ours has
  one. Per-pixel scatter may be exactly what one scale buys you.

Option (c) is worth dwelling on, because it is the one that is not a fix. If the
scatter is what a single scale genuinely gives, then the honest response is to
report that, not to widen a window until the number complies.

Issue #1 remains open on this.

## What this test does not rule out

The most important caveat is about the falsifier that *passed*.

Gain invariance separates this encoder from a differencing one. It does **not**
separate it from a squared-cross-correlation-of-raw-pixels fake, because the
`argmax` of anything of the form `gain^n · f_k(x)` is gain-invariant regardless of
what mechanism produced `f_k`. The docstring says so; so does `findings.md`. A
positive result here is consistent with the mechanism we claim and does not
establish it.

Two more, both structural:

- **Constant-disparity stimuli validate sanity, not sufficiency.** Every test used
  a single flat disparity. Nothing here says anything about slanted surfaces or
  depth discontinuities — the same trap exp001 fell into with the `disk` stimulus.
- **`synthetic_pair` bypasses L1 entirely.** No projection, no rectification. This
  says nothing about rendered or real imagery.

## Where this leaves L2

**Nothing in the pipeline consumes this encoder.** Outside its own unit tests,
`GaborEnergyEncoder` is imported by exactly one file: exp002's own runner. No
matcher in `inference/` reads a response volume.

That is not an oversight, it is a missing piece. Connecting L2 to L3 requires a
**decoder** — something that turns a `(K, H, W)` population response into an
`Estimate` with a variance — and it does not exist. Until it does, exp002's result
is a statement about a component in isolation rather than about the system.

Which makes one deferred idea more interesting than it looks. The encoder's gain
invariance is *exact*, and [exp003](exp003-appearance-and-matching.md) later found
that differential interocular shading is precisely where SSD matching struggles.
An energy-model front end has a principled reason to be better there. Testing that
needs the decoder first — which is why it was explicitly ruled out of scope at the
time rather than attempted.

The other reason to want the decoder is sharper still. A population profile
carries its own uncertainty in its *shape*, where the block matcher has to infer
uncertainty from cost curvature — the very quantity
[exp004 found to be anti-calibrated](exp004-real-data-transfer.md) in
half-occlusions. A decoder reading peak *sharpness relative to the whole profile*
would be attacking that problem from a different direction than
[#8](https://github.com/visgraf/active-stereo/issues/8) proposes.

## Reproducing

```bash
python -m experiments.exp002_energy_model_validation.run \
    --config experiments/exp002_energy_model_validation/config.yaml
```

Bank resolution (`encoding.bank.step`) sets its own tolerance and was fixed once,
here. It must not be retuned later to make this result pass.
