# ADR-0007: Render with off-axis frusta, and note that L1 is not the Vieth–Müller model

- **Status:** Accepted
- **Date:** 2026-08-15
- **Context of discovery:** Configuring the Blender stereo camera

## Context

Setting up `scripts/render_stereo.py` forced a choice between Blender's two
stereo convergence modes, and doing so surfaced a **latent inconsistency inside
L1** that had gone unnoticed because the two halves were never used together.

`geometry/projection.py` implements

    d = f·b·(1/Z − 1/Z_f)

which depends on `Z` alone. Its zero-disparity locus is therefore a
**fronto-parallel plane** at the fixation distance. That is the *shifted-frustum*
(off-axis) rig: two parallel optical axes with a horizontal image-plane shift.

`geometry/horopter.py` computes the **Vieth–Müller circle**, whose radius
`R = b / (2 sin μ)` follows from the inscribed-angle theorem. That is the
zero-disparity locus of a *toed-in* rig, where the eyes rotate to converge — the
biological case.

These are different rigs. Near the fixation axis they agree to first order, which
is why the discrepancy stayed hidden, but they diverge with eccentricity, and
eccentricity is exactly the variable ADR-0003 makes the pipeline sensitive to.
A rendered scene using toe-in would have quietly injected that divergence into
every foveal-confinement result.

Toe-in has a second cost: rotating the cameras introduces **vertical disparities**
that grow with eccentricity, which the framework does not model at all.

## Decision

1. Render with Blender's `OFFAXIS` convergence mode. It matches
   `depth_to_disparity` exactly and produces no vertical disparity.
2. Treat `vieth_muller_circle` as documentation of the *biological* horopter that
   L1 approximates near the fixation axis — not as the horopter of the rig L1
   models. Its docstring and `docs/architecture.md` say so explicitly.
3. Record this as an open modelling question rather than pretending it is closed.

## Alternatives considered

- **Toe-in rendering, to match the Vieth–Müller horopter.** Rejected for now: it
  would make the stimulus inconsistent with L1's projection, so matcher error and
  model error would be inseparable. Revisit only alongside item 4 below.
- **Delete the Vieth–Müller code.** Rejected: the circle is the correct target
  for a framework that claims to model *biological* stereopsis, and deleting it
  would hide the gap rather than close it.
- **Add a small correction term to L1.** Rejected as premature. The right move is
  a toed-in projection model derived properly, not a fudge factor fitted to the
  difference.

## Consequences

- Rendered and synthetic stimuli share one projection model, so results are
  comparable across them.
- The framework's biological claim is now explicitly weaker than it looked: it
  models a shifted-frustum rig, and the Vieth–Müller horopter is an aspiration.
  **This must be stated in the paper**, not discovered by a reviewer.
- **Open work (item 4):** derive a toed-in projection for L1, including vertical
  disparity, and quantify the divergence from the off-axis model as a function of
  eccentricity. Until then, quantitative claims about peripheral depth carry a
  systematic error of unknown size.

## Verification

`tests/unit/test_geometry.py::test_zero_disparity_on_the_horopter` pins the
planar zero-disparity locus. `scripts/render_stereo.py` sets `OFFAXIS` and records
`convergence_mode` in `rig.json`, so any render made under a different assumption
is identifiable after the fact.

No test yet covers the divergence itself; writing one is part of item 4.
