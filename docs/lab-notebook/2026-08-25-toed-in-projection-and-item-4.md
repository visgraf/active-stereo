# 2026-08-25 — Toed-in projection: ADR-0007 item 4, closed

Branch `feat/toed-in-projection`, migration step 4a + 4b
([plan](../plans/toed-in-projection.md)). Second entry of this date; the first
is [the plane-of-regard optimum](2026-08-25-plane-of-regard-optimum.md), which
this builds on.

[ADR-0007](../decisions/0007-offaxis-not-toein.md) left item 4 open: *derive a
toed-in projection for L1, including vertical disparity, and quantify the
divergence from the off-axis model as a function of eccentricity.* Both halves
are done here. All figures are computed from
`activestereo.geometry.project_toed_in` / `toed_in_disparity` at this branch's
HEAD.

## 1. The divergence from the off-axis model — item 4's real content

ADR-0007 says the two models "agree near the fixation axis and diverge with
eccentricity". That is true and it is not the whole shape. The signed difference
`d_h(toed-in) − d_h(off-axis)`, for a point at Cartesian depth `Z` and in-plane
eccentricity `η`, decomposes into **two independent terms**:

    D(Z, η)  =  e0(Z/Z_f)  +  c·η²

`e0` is the eccentricity-independent part, and it does not vanish anywhere
except on the horopter itself:

| Z / Z_f | e0 (px), b = 0.064 | b = 0.032 | b = 0.016 |
|---|---|---|---|
| 0.7 | **−3.208519e-2** | −3.208519e-2 | −3.208519e-2 |
| 1.0 | 1.948105e-14 | 1.948105e-14 | 1.948105e-14 |
| 1.4 | **+1.070289e-2** | +1.070289e-2 | +1.070289e-2 |

(μ = 0.064, f = 800 px, k = 0.25.) Two properties worth having on the record:

- **`e0` is baseline-independent** — identical to every printed digit across a
  4× range of baselines. At a fixed *depth ratio* both models scale as
  `f·b/Z_f = f·2tan(μ/2)`, so `b` cancels; `e0` is a property of the vergence
  and the depth ratio alone.
- **`e0` changes sign across the horopter**, negative nearer than fixation and
  positive beyond it. So it is not an offset that could be absorbed into a
  calibration constant.

A test phrased as "the models agree to within ε near the axis" would have hidden
`e0` inside ε and pinned nothing. The two assertions that replace it are
tolerance-free: the models agree to machine zero at `η = 0, Z = Z_f` (1.95e-14
px), and the **signed** residual `D(η) − D(0)` quarters as `η` halves —

| ladder η | 0.10 → 0.05 | → 0.025 | → 0.0125 | → 0.00625 |
|---|---|---|---|---|
| ratio | 4.0201 | 4.0050 | 4.0013 | 4.0003 |

identical at all three depths, converging on the exact integer 4 from above.

**Signed is load-bearing, not stylistic.** At 1.4 Z_f, `e0 > 0` while `c·η² < 0`,
so `D(η)` crosses zero near **η ≈ 0.0143** — inside any natural ladder
(−2.13e-2 at η = 0.025, +2.40e-4 at η = 0.0143, +1.07e-2 at η = 0). An
`|·|`-based ladder straddling that crossing gives ratios 4.22 / 4.63 / 10.08 and
means nothing. This is the second time in three days that taking an absolute
value destroyed a structural result (cf. the τ-table tolerance in the companion
entry); both times the signed quantity was the well-behaved one.

## 2. The horopter closure

The Vieth–Müller circle is the zero-horizontal-disparity locus of the toed-in
model, in three regimes that need three different statements:

| regime | max \|d_h\| |
|---|---|
| `azimuth == 0` or `elevation_down == 0`, any μ, any k | ≤ 2e-13 px — **exact** |
| oblique, k = 0 | follows `x·μ·az·el²·(k−½)/2` to **2.2%** |
| oblique, k = 0.25 | follows the same law to **5.6%** |
| oblique, k = 1/2 | 2.0e-3 px — a residual the law does not capture |

Sampled on the circle to the image edge (|x| ≤ 160 px, the 320-px image at
f = 800 px). The k = 1/2 corner is bounded absolutely rather than by relative
error: the law *predicts zero* there and the measurement is not zero, so a
relative pin would be a division by a vanishing quantity.

**Negative control.** Perturbing `fixation.vergence` by 1% and re-projecting the
**unperturbed** circle moves `|d_h|` to 0.5325 px, against the predicted scale
`f·δμ` = 0.512 px (4%). The margin is regime-dependent, and both are recorded
because quoting only the first would overstate the test: ~13 orders in the
exact-zero regime (5.7e-14 → 0.53), but only ~40× at oblique gaze
(3.4e-2 → 1.36), where the unperturbed value is already the ADR-0016 residual.

## 3. Vertical disparity — the step-3 promise, discharged

[The step-3 entry](2026-08-23-listing-l1-vs-l2-scale.md) lines 33–35 recorded
δy ≈ x·Δτ as **first-order estimates only**, and promised the exact figures from
step 4's projection. Here they are — differential vertical disparity between
k = 0.25 and k = 0, at the point of the Vieth–Müller circle whose left-image
column is 160 px (az = 0.197, el = 0.149):

| fixation depth | μ (rad) | first-order δy | **exact \|Δd_v\|** |
|---|---|---|---|
| 1.0 m | 0.0640 | 0.38 px | **0.3784** |
| 0.7 m | 0.0914 | 0.54 px | **0.5403** |
| 0.4 m | 0.1597 | 0.94 px | **0.9436** |

**The first-order estimates are confirmed to better than 0.5%.** The linearisation
δy ≈ x·Δτ was sound at project scales, and the step-3 caution was warranted but
not, in the event, load-bearing.

What that table did *not* record is the quantity a matcher actually sees — the
**total** vertical disparity, not the k-difference. On the same circle, sagittal
gaze, el = 0.149, |x| ≤ 160 px:

| fixation depth | μ (rad) | k = 0.25 | k = 0 |
|---|---|---|---|
| 1.0 m | 0.0640 | 0.3821 px | 0.7640 px |
| 0.7 m | 0.0914 | 0.5459 px | 1.0913 px |
| 0.4 m | 0.1597 | 0.9544 px | 1.9064 px |

Against the in-repo benchmarks: exp007's MiddEval3 `dyavg` reaches ≈ 0.5 px at Q;
the matchers' median |Δd| is 0.0714 px (block) and 0.0074 px (energy bank) on RDS.
At the current default the total is at or above measured rectification error and
one to two orders above matcher precision. ADR-0016's consequence stands
unchanged: this is contaminated by the unsettled `k` and is not yet usable as an
L4 cue.

## 4. What is closed, and what still says otherwise

Item 4 is closed **in substance**: the toed-in projection exists, it produces
vertical disparity, and the divergence from the off-axis model is quantified as a
function of eccentricity in §1. The off-axis model is retained unchanged and its
tests are untouched — `depth_to_disparity` still describes how every stimulus in
the repo was captured.

Three places still read as though it were open, deliberately:

- `docs/decisions/README.md` lists ADR-0007 as "Superseded by 0013";
- `horopter.py`'s module docstring still says "this is **not** the horopter of
  the rig that `geometry/projection.py` models";
- ADR-0007's own Consequences still describe item 4 as open work (and, being an
  ADR, will never be edited).

The first two are rewritten at **migration step 12**, which owns the
documentation sweep; the third is corrected the way ADRs are corrected, by a
successor. Recorded here so the gap between substance and index is a known state
rather than an oversight.

## 5. Provenance

Every figure is computed in-repo at this branch's HEAD. The load-bearing ones are
pinned by `tests/unit/test_projection_toedin.py`; the rest are measurements
recorded with their sampling window and asserted nowhere. The k = 1/2 per-eye
meridian pin discriminates at 8.1e-6 px for a 1e-5 relative perturbation of k,
against a 1e-12 px tolerance — it cannot pass vacuously.
