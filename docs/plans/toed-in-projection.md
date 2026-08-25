# Plan: toed-in projection and the ADR-0007 item-4 closure

Migration step **4a + 4b** of [`fixation-migration.md`](fixation-migration.md).
Branch `feat/toed-in-projection`, off `main` at `f9b62f8`. One PR, **separate
acceptance criteria for 4a and 4b**.

Companions: [ADR-0007](../decisions/0007-offaxis-not-toein.md) (item 4 is what
this closes), [ADR-0013](../decisions/0013-fixation-as-oculomotor-state.md),
[ADR-0015](../decisions/0015-helmholtz-gaze-composition.md),
[ADR-0016](../decisions/0016-plane-of-regard-alignment-optimum.md).

## Why

`geometry/projection.py` models a shifted-frustum rig, `d = f·b·(1/Z − 1/Z_f)`,
whose zero-disparity locus is a fronto-parallel plane. ADR-0007 recorded that
this is *not* the Vieth–Müller horopter the framework claims to model, and left
**item 4** open: derive a toed-in projection including vertical disparity, and
quantify the divergence from the off-axis model as a function of eccentricity.

Step 3 supplied the missing piece (`geometry/oculomotor.eye_rotations`), and
ADR-0016 established what the resulting geometry actually does. This step closes
item 4.

**Additive throughout.** `depth_to_disparity` / `disparity_to_depth` and their
tests are untouched — they pin the retained off-axis *capture* model, and
`test_zero_disparity_on_the_horopter` continues to pin its planar locus.

## 4a — per-eye toed-in projection

`src/activestereo/geometry/projection.py`:

- `BinocularProjection` — frozen dataclass, `left` / `right`, each `(..., 2)` in
  **(row, col) pixels**. A named pair rather than a tuple, for the reason
  `EyeRotations` is one: an `R, L = ...` unpack swap is silent at the call site.
- `project_toed_in(points, rig, fixation, k=0.25) -> BinocularProjection`.
  `points` is `(..., 3)` **metres, cyclopean head frame**, so the same function
  serves an `(H, W, 3)` grid and an `(N, 3)` sample set. Per eye,
  `v = (P − C_e) @ R_e` with `R_e` from `eye_rotations`; then
  `row = f·v_y/v_z + c_row`, `col = f·v_x/v_z + c_col`. Points with `v_z ≤ 0` or
  non-finite input become `np.nan` in **both** channels (CLAUDE.md §3 — never 0,
  never a sentinel).
- Exported from `geometry/__init__.py`.

### 4a acceptance — `tests/unit/test_projection_toedin.py`

- **A1 — optical axis.** The fixation point images on the principal point in both
  eyes, < 1e-9 px, across the az × el × μ × k sweep. **Torsion-blind, and its
  docstring says so:** injecting a roll `R_e · R_z(θ)` leaves this test passing to
  3.6e-14 px at θ = 1.2 rad. It pins the optical axis and nothing else.
- **A2 — per-eye meridian.** At `k = 1/2` and sagittal gaze, points in the plane
  of regard image on **each eye's own** horizontal meridian:
  `max |row_e − c_row| < 1e-12` px, asserted on left and right **separately**.
  Negative control `> 0.05 px` at `k ∈ {0, 0.25}`. A differential test passes when
  both eyes are wrong the same way; this one cannot.

  Reference magnitudes (docstring only, never asserted — the window is angular,
  ±0.197 rad, reaching |x| = 170–184 px off a 320-px sensor, so these move with
  it): 0.2031 / 0.4061 px at μ = 0.064 and 0.5500 / 1.0987 px at μ = 0.1597, for
  k = 0.25 / 0. Note per-eye is **not** half the differential (0.2031 vs 0.3813):
  `y_L` and `y_R` are mirror-antisymmetric in `x`, so their maxima fall at
  different points.
- **A3 — divergence from the off-axis model, tolerance-free.** "First-order
  agreement near the axis" conflates two independent terms. The signed difference
  against `depth_to_disparity` decomposes as `e0(Z/Z_f) + c·η²`, where `e0` is the
  `η = 0` term and is both eccentricity- and **baseline-independent**:

  | Z/Z_f | e0 (px) | b = 0.064 / 0.032 / 0.016 |
  |---|---|---|
  | 0.7 | −3.208519e-2 | identical to all printed digits |
  | 1.0 | 1.948105e-14 | identical |
  | 1.4 | +1.070289e-2 | identical |

  `e0` changes sign across the horopter, and a tolerance-based test buries it.
  Two tolerance-free assertions instead:

  1. at `η = 0`, `Z = Z_f` the two models agree to machine zero (1.95e-14 px);
  2. the **signed** difference minus its `η = 0` value quarters as `η` halves —
     ladder 0.10 → 0.05 → 0.025 → 0.0125 → 0.00625, ratios 4.0201 / 4.0050 /
     4.0013 / 4.0003, identical at all three depths.

  **Signed is load-bearing.** At 1.4 Z_f, `e0 > 0` while `c·η² < 0`, so `D(η)`
  crosses zero near `η ≈ 0.0143` — inside any natural ladder (−2.13e-2 at
  η = 0.025, +2.40e-4 at η = 0.0143, +1.07e-2 at η = 0). An `|·|`-based ladder
  straddling that gives ratios 4.22 / 4.63 / 10.08 and means nothing.
- **A4** behind-eye and non-finite points → `nan` in both channels.
- **A5** principal-point offset honoured, in (row, col) order.

## 4b — vertical disparity and the horopter closure

- `toed_in_disparity(points, rig, fixation, k=0.25) -> (d_h, d_v)`, pixels.
  `d_h = col_L − col_R`, positive = crossed (CLAUDE.md §3). **`d_v = row_L −
  row_R` is a new quantity, and its convention is defined once, here.**
- `horopter.vieth_muller_points(rig, fixation, azimuths) -> (..., 3)` metres,
  cyclopean head frame, in the plane of regard. It **owns the
  `R_x(elevation_down)` rotation**: a function taking a `Fixation` and returning
  XZ-plane samples would silently ignore `elevation_down`, and a test applying
  the rotation by hand is precisely the private frame re-derivation ADR-0015's
  consequences clause forbids. `azimuths` is required, so no arbitrary sampling
  constant enters the library. `vieth_muller_radius` / `vieth_muller_circle` are
  **not** given an optional `fixation` parameter.

### Which vergence field each guard reads — `fixation.vergence`, throughout

Under ADR-0013 a refixable rig has `rig.vergence == 0`, and the 4b sweep runs on
one. A guard reading `rig.vergence` would raise in **exactly the case B1
exercises**, and a precondition computed through `vieth_muller_radius(rig)` would
receive `inf` and pass vacuously — the hazard `fixation-migration.md` lines 69-85
names. Therefore:

- `vieth_muller_points` raises on `fixation.vergence <= 0`;
- B1's precondition computes `R = rig.baseline / (2·sin(fixation.vergence))`;
- B3's test-local circle uses `h = (b/2)/tan(fixation.vergence)` and
  `R = b/(2·sin(fixation.vergence))`.

`vieth_muller_points` states this in its docstring, **because
`vieth_muller_radius(rig)` remains in the same module reading the other field** —
two functions, two vergence sources, one module, so the distinction is written
down rather than inferred.

### 4b acceptance

Preconditions asserted before any disparity is compared: `isfinite(R)`,
`fixation.vergence > 0`, points finite and non-empty, and actually projecting
inside the image. The sweep runs on a **`vergence = 0` rig with an explicit
`Fixation`**, so the ADR-0013 hazard is exercised rather than described.

- **B1 — the payoff.** `|d_h| < 1e-12` px wherever `az == 0` **or** `el == 0`
  (measured ≤ 2e-13). At oblique gaze the residual follows
  `x·μ·az·el²·(k−½)/2`, pinned at **k ∈ {0, 0.25} only**, 10% rel. (measured 2.2%
  and 5.6%). At `k = 1/2` the law vanishes and the measurement does not, so that
  corner takes an **absolute** bound, `|d_h| < 5e-3` px (measured 2.0e-3),
  documented as a residual the law does not capture.
- **B1v — vertical disparity is nonzero by design.** Threshold **0.05 px**, far
  below both candidate criteria (circle 0.38–0.95 px, plane 0.41–1.11 px). The
  point set is named in the test name and the docstring, which also states that
  ADR-0016 leaves plane-vs-circle open and that this asserts **non-vanishing
  only, not a magnitude**. Doubles as the guard against a projection returning
  zeros.
- **B2 — negative control.** Perturb `fixation.vergence` by 1%; `|d_h|` on the
  *unperturbed* circle must then exceed tolerance. Measured 0.5325 px against
  predicted `f·δμ` = 0.512 px. Two regimes, reported separately: exact-zero
  configurations move 5.7e-14 → 0.5325 (ratio 9.4e12), oblique 3.4e-2 → 1.36
  (ratio 40).
- **B3** `vieth_muller_points` against an independent test-local circle, 1e-15 m
  — the compensating control for the library owning `R_x`.
- **B4** a degenerate rig raises.

## Deliberately out of scope

This step does **not** resolve the plane-vs-circle criterion, run the ADR-0014
k-sweep, re-derive ADR-0003's linearisation bound under toed-in geometry, or
touch the ADR hook predicate ([#32](https://github.com/visgraf/active-stereo/issues/32)).
Closing 4b needs none of them: B1's exact-zero regime and the residual law are
circle-only statements, true independently of which criterion is adopted; B1v
asserts non-vanishing with its point set named; A3 is tolerance-free and cites no
peripheral bound.

**Item 4 is closed in substance here, not in the index.**
`docs/decisions/README.md` still lists ADR-0007 as "Superseded by 0013", and
`horopter.py`'s module docstring still disclaims ("this is **not** the horopter
of the rig that `geometry/projection.py` models"). Both are rewritten at
**migration step 12**, which owns the documentation sweep.
