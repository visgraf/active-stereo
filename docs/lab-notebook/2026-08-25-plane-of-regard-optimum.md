# 2026-08-25 — The plane-of-regard alignment optimum is k = 1/2

Branch `docs/adr-0016-plane-of-regard-optimum`. Companion to
[ADR-0016](../decisions/0016-plane-of-regard-alignment-optimum.md), and a
correction to [ADR-0014](../decisions/0014-listing-coefficient-as-parameter.md).

Derived while fixing the acceptance tolerance for migration step 4 *before*
writing the test. The tolerance derivation went wrong (§7), and chasing why
turned up the result below, which fires ADR-0014's own standing pin
(`0014:116-118`).

**Result.** Vertical disparity in the plane of regard is nulled at
**k = 1/2**, not at k = 0.25. At sagittal gaze the null is exact — machine
zero, not a minimum — and independent of baseline, focal length, vergence and
elevation. No `src/` code changed: `eye_rotations` is correct; the claim in
ADR-0014 about which `k` it implies is not.

## 1. Why it is exact: the Helmholtz identity

The reason is stronger than a cancellation of leading terms. **At `k = 1/2` and
sagittal gaze, the tilted-Listing composition `A(p_e→g_e) · A(ẑ→p_e)` *is* the
Helmholtz rotation `R_x(el_e) · R_y(az_e)` of that eye's own gaze**, identically:

| el | μ | k = 0 | k = 0.25 | k = 0.5 |
|---|---|---|---|---|
| 0.149 | 0.064 | 2.387e-03 | 1.194e-03 | **2.637e-16** |
| 0.149 | 0.160 | 5.955e-03 | 2.981e-03 | **1.110e-16** |
| 0.300 | 0.350 | 2.611e-02 | 1.313e-02 | **1.110e-16** |
| 0.050 | 0.020 | 2.500e-04 | 1.250e-04 | **2.621e-15** |

(max ‖R − R_x R_y‖_∞ over both eyes, dimensionless; `az_e`, `el_e` read off the
eye's gaze direction.)

ADR-0015 established that Helmholtz composition carries **no torsion about the
plane of regard** — that is the planarity property the whole ADR rests on. So at
`k = 1/2` the plane of regard images on the horizontal meridian of *both*
retinas, and vertical disparity vanishes there for every point of the plane at
once, at any depth, exactly. The optimum is not a coincidence of the projection;
it is ADR-0015's planarity seen from the oculomotor side.

This also explains the config-independence: an identity between rotations cannot
depend on `b` or `f`, which never enter it.

## 2. The first-order derivation, as the linearisation of §1

Strict Listing twists each eye's image meridian relative to the plane of regard
by `ψ_e⁰ ≈ −az_e · el / 2` (spherical excess of the ẑ–p_e–g_e triangle); the
temporal primary tilt contributes `+ k · μ · el / 2` by the same mechanism. At
symmetric fixation `az_e = ±μ/2`, so

    ψ_e ≈ −μ·el/4 + k·μ·el/2   →   ψ_e = 0  at  k = 1/2,

with `b`, `f`, `el` and `μ` all dropping out. Measured against the closed form:

| el | μ | k | ψ_L measured (rad) | first-order |
|---|---|---|---|---|
| 0.149 | 0.064 | 0.00 | −2.389e-03 | −2.384e-03 |
| 0.149 | 0.064 | 0.25 | −1.195e-03 | −1.192e-03 |
| 0.149 | 0.064 | 0.50 | **8.674e-19** | 0 |
| 0.300 | 0.350 | 0.00 | −2.651e-02 | −2.625e-02 |
| 0.300 | 0.350 | 0.50 | **1.388e-17** | 0 |

The linear form is 0.2% off at project scales and 1% off at el = 0.3, μ = 0.35 —
but the null it predicts is exact even where the form itself is not, because §1
holds beyond first order. The `/2` here is the same spherical excess disarmed in
[2026-08-23](2026-08-23-listing-l1-vs-l2-scale.md) lines 60–68; it is **not** the
Tweed–Vilis half-angle rule, which is velocity-domain.

## 3. ADR-0014's sign/axis clause, discharged

ADR-0014:118 instructs that a minimum away from 0.25 "be read as an
`eye_rotations` sign/axis error until proven otherwise". It is not one.

`eye_rotations` was reimplemented independently — Rodrigues by explicit
axis-angle with trigonometry (the module uses the trig-free
`I + [v]× + [v]×²/(1+c)` form), and the fixation point by bisection on the
subtended angle (the module uses the closed-form Vieth–Müller chord). Over a
grid of **144** (az, el, μ, k) configurations including eccentric azimuth:

    max ‖R_independent − R_library‖_∞  =  4.021e-15  =  18 ε

and the reimplementation reproduces `k_null = 1/2`.

**On "bit-identical" as a criterion.** Only 2/144 configurations agreed
bit-for-bit, and that is the *expected* outcome, not a weakness: a
reimplementation that agreed bit-for-bit would have retraced the same
floating-point path and checked nothing. Agreement at 18 ε through different
algebra is the stronger result. An earlier check that did agree bit-identically
reused the module's own Rodrigues form and is recorded here as the weaker of the
two.

## 4. Two criteria, two floors — the null is exact only at sagittal gaze

Off-axis there is an irreducible floor: no `k` aligns the plane of regard when
gaze is neither sagittal nor horizontal. **The magnitude depends entirely on
which point set the criterion is taken over**, and the two answers differ by four
orders of magnitude, so the criterion must always be named.

Window for both columns: in-plane azimuth φ ∈ [az−0.5, az+0.5], 2001 samples,
restricted to |x_L| ≤ 160 px (the image edge at f = 800); `k` minimised over
[0.30, 0.70] in 4001 steps. b = 0.064 m, f = 800 px, el = 0.149, μ = 0.064.

| az | **plane** floor (px) | argmin k | VM-**circle** floor (px) | argmin k |
|---|---|---|---|---|
| 0.000 | 0.0000 | 0.5000 | 3.386e-16 | 0.5000 |
| 0.130 | 0.2129 | 0.4921 | 7.246e-05 | 0.5042 |
| 0.197 | 0.3231 | 0.4815 | 6.710e-05 | 0.5098 |
| 0.250 | 0.4109 | 0.4696 | 2.079e-05 | 0.5160 |
| 0.350 | 0.5781 | 0.4374 | 1.425e-05 | 0.5322 |

The plane set is radial depths {0.7D, 1.0D, 1.4D}; the circle set is the
Vieth–Müller circle, a single curve *inside* that plane.

**Tweed's criterion is the plane, not the horopter curve within it**, so the
plane column is the one ADR-0016 is about. Note the argmin drifts *below* 1/2 on
the plane and *above* it on the circle — opposite directions, from the same
rotations. A floor quoted without its point set is meaningless.

No test pins the floor. It is real, but its magnitude is a function of the
sampling window, and pinning a window-dependent number is how a test becomes a
tripwire for the sampling grid rather than for the physics.

## 5. What k = 0.25 costs

max |row_L − row_R| in pixels over the plane of regard, same window, k = 0.25:

| fixation depth | μ (rad) | az = 0 | az = 0.197 | az = 0.35 |
|---|---|---|---|---|
| 1.0 m | 0.0640 | 0.4076 | 0.6443 | 0.8244 |
| 0.7 m | 0.0914 | 0.5968 | 0.9074 | 1.1693 |
| 0.4 m | 0.1597 | 1.1100 | 1.5303 | 2.0030 |

Benchmarks unchanged from [2026-08-23](2026-08-23-listing-l1-vs-l2-scale.md):
exp007's MiddEval3 `dyavg` reaches ≈ 0.5 px at Q; the matchers' median |Δd| is
0.0714 px (block) and 0.0074 px (energy bank) on RDS. **At the current default
the in-plane vertical disparity exceeds measured MiddEval3 rectification error
and is one to two orders above matcher precision.** Off-axis gaze and the
`k = 0.25` choice degrade alignment comparably (0.21–0.58 px vs 0.41–1.11 px at
az = 0); neither dominates, and no `k` repairs the off-axis component.

## 6. Three corrections on the record

**The on-circle vertical disparity at k = 0.25 is not the L4 cue.** It was read
that way in the step-4 briefing. At k = 1/2 it is zero in the plane of regard, so
what remains at 0.25 is a **torsional misalignment artefact of the current
default** — and it is the same order as the genuine vertical-disparity distance
cue it would be confused with. Consequence, recorded so it is not rediscovered:
**L4 vertical-disparity cue work is contaminated until k is settled.** A cue and
an artefact of comparable size in the same channel cannot be separated by
measuring that channel.

**The tolerance prediction that started this failed by dropping ψ⁰.** The step-4
briefing predicted an on-circle horizontal residual of order 1e-6 px from the
τ-table alone, as `x·(τ_R² − τ_L²)/2`. Measured: exactly zero (≤ 2e-13 px) where
`az = 0` or `el = 0`, and ~3.4e-2 px at oblique gaze — four orders high. The
omitted term is `ψ⁰ ≈ −az_e·el/2`: the τ table is torsion measured *relative to
strict Listing*, and strict Listing is itself tilted relative to the plane of
regard. The governing quantity is the total meridian tilt `ψ_e = ψ_e⁰ + τ_e`.

This is logged as a **handoff-contract failure** (CLAUDE.md §5), not merely a
wrong number: `ψ⁰` is the same term as §2's own derivation, supplied in the same
thread. The prediction and the derivation that refutes it were both available at
the time; only the prediction was carried forward. That is the failure mode the
contract exists to catch, and it was caught by deriving before running, which is
why the tolerance was never written into a test.

**The window-spread figure quoted in review was measured on a sensor that does
not exist.** Reviewing §5, the plane-of-regard cost was challenged as
irreproducible without its window, on the evidence that the rms moved ~1.5×
across defensible windows — 0.230 px at ±0.197 rad at horopter depth against
0.354 px over 0.4–2.5 D at ±0.30 rad (b = 0.064, f = 800, el = 0.149,
μ = 0.064). The 0.354 was computed **unclipped**: a ±0.30 rad fan reaches
|x| ≈ 247 px at f = 800, off the edge of a 320-px image. Clipped to |x| ≤ 160 px
at n = 2001 the three windows give **0.2189 / 0.2267 / 0.2203 px** — agreement
to 4%, not a 1.5× spread.

The reproduction gap in the other direction was a metric, not a window: §5 quotes
**max**, the review computed **rms**, and over one fixed window those differ by
1.8× (0.4076 px against 0.2203 px at μ = 0.064). That is the real sensitivity,
and it is why [ADR-0016](../decisions/0016-plane-of-regard-alignment-optimum.md)
quotes Vieth–Müller-circle figures with the image half-width stated in the
sentence: the circle has one free parameter that the rig fixes, the plane has
three that the analyst picks.

**The challenge was right on a wrong number, and the resolution stands
unchanged.** Same class as the ψ⁰ error above, and the same provenance: both
arrived as hypotheses with pointers rather than as values, both were checked
against the files before anything durable was written, and both were caught for
that reason. Two of the three corrections in this section are of that shape,
which is the argument for the handoff contract stated as an outcome rather than
as a policy.

## 7. Provenance

Every figure above is computed in-repo from `activestereo.geometry.eye_rotations`
at this branch's HEAD, via the independent constructions described in §1–§3. The
two load-bearing statements — §1's identity and the k = 1/2 null — are pinned by
`tests/unit/test_oculomotor.py::test_tilted_listing_at_k_half_is_helmholtz` and
`::test_plane_of_regard_alignment_optimum_is_k_half`; the rest are measurements
recorded with their window and are not asserted anywhere.
