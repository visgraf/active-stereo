# ADR-0017: The rectification rotation is the Helmholtz version rotation with azimuth zeroed

- **Status:** Accepted
- **Date:** 2026-08-25
- **Context of discovery:** migration step 5, planning `target_to_fixation`
  (`docs/lab-notebook/2026-08-25-step-5-target-to-fixation.md`)

## Context

`target_to_fixation` must unproject a pixel, which requires the orientation of
the frame that pixel is in. Under ADR-0013:93-97 that frame is the **rectified**
one — L2/L3 consume the rectified pair, and ADR-0013:169 fixes bare "disparity"
to mean pixels in the rectified frame. So the pixel→rotation boundary cannot be
written without `R_rect`.

`R_rect` did not exist. It occurred exactly once in the repository, as an
**undefined symbol** in the migration plan's step 6 formula
(`docs/plans/fixation-migration.md:121`); nothing said how it is chosen, and
`geometry/rectify.py` had not been written. Step 5 needs it before step 6 does.

The substantive point is that **`R_rect` is not determined by the requirement to
rectify.** Rectification needs only that the two eyes share an orientation and
that their optical centres be displaced along the resulting image x-axis. The
centres differ along the head `+X` axis, so *every* rotation about that axis
satisfies both conditions. Verified: for `R_x(θ)` at
`θ ∈ {−0.90, −0.20, 0.00, 0.37, 1.10}` the induced vertical disparity is
`0.000e+00` — exactly zero, not small — over 400 sample points.

A one-parameter family therefore rectifies equally well, and a reader who finds
a specific matrix in the code cannot tell what is forced from what was chosen.
Recording that freedom is most of this ADR's value.

## Decision

`geometry/oculomotor.rectification_rotation(fixation)` returns the **Helmholtz
version rotation (ADR-0015) with azimuth zeroed** — `helmholtz_rotation(0,
fixation.elevation_down)` in the sense of `tests/unit/test_oculomotor.py`:

    R_rect = [[1,  0,       0     ],
              [0,  cos el,  sin el],
              [0, -sin el,  cos el]]

**Direction: rect → head**, the same convention as `EyeRotations`
(`R @ [0,0,1]` is the frame's optical axis in the head frame), so consumers
project with `R.T`.

**The member is selected by the principal-row criterion:** it is the one that
images the fixation point on the principal row, for every azimuth and vergence
(verified to 1.1e-13). This is ADR-0016's plane-of-regard criterion restated at
the level of the image.

It lives in `geometry/oculomotor.py` because that module's docstring states gaze
becomes SO(3) there **and nowhere else**; putting an SO(3)-from-gaze function in
`rectify.py` would contradict it.

Azimuth-independence is structural, not empirical: under Helmholtz composition
the plane of regard is the elevated plane for every azimuth (ADR-0015), so
zeroing azimuth loses nothing.

## Alternatives considered

**Any other member of the family** (`R_x(θ)` for `θ ≠ elevation_down`). Rejected
not because it fails to rectify — it does not fail; `d_v` is identically zero for
all of them — but because it moves the fixation point off the principal row for
no gain. There is no second criterion pulling the other way, which is precisely
why this needs recording: the choice is free, and a later reader must not infer
from the code that it was forced.

**Including azimuth**, i.e. aligning the rectified optical axis with the
cyclopean gaze (`R_x(el)·R_y(az)`). This is the intuitive choice and it is
**wrong**: it rotates the image x-axis off the baseline, so the pair is no longer
rectified at all. Measured `max |d_v|` = 9.3 px at `az = 0.1`, 35.6 px at
`az = 0.3`, 84.9 px at `az = 0.5`. The rectified frame is therefore *not* a
gaze-centred frame, and at eccentric fixation the fixation point does not land at
the image centre — only on the centre row.

**Deferring to step 6 / `geometry/rectify.py`.** Rejected on two counts: it
contradicts `oculomotor.py`'s single-SO(3)-site claim, and it does not define the
symbol, it only moves the undefined symbol later. Step 5 needs the definition
regardless of which file eventually owns the warp.

**Taking the L6 target in raw left-eye pixels**, avoiding `R_rect` entirely.
Rejected: the L3 disparity field and the saliency map derived from it are already
in the rectified frame, so this un-rectifies a natively rectified pixel and puts
a frame conversion in L6 — a second convention (CLAUDE.md §4) on top of
contradicting ADR-0013:93-97 and :169.

## Consequences

**`k` is not an input.** `R_rect` depends on elevation alone, so the Listing
coefficient never enters. This is triviality, not robustness — `k` is not a
variable that was swept and found not to matter, it is a variable that never
appeared — and the docstring says so rather than letting a reader infer a
swept invariance from a list of independent parameters.

**Step 6 inherits the definition, and a correction.** The homography is

    H_e = K R_rectᵀ R_e K⁻¹        (raw eye -> rectified)

Migration plan step 6 as written had `K R_rect R_eᵀ K⁻¹`, which is wrong in
**factor order** — measured error 2.7e+04 px eye→rect and 2.7e+02 px rect→eye,
i.e. incorrect in *both* directions under either reading of `R_rect`. The correct
forms are `K R_rectᵀ R_e K⁻¹` (eye→rect, 9.1e-13 px) and `K R_eᵀ R_rect K⁻¹`
(rect→eye, 3.4e-13 px). The plan file is corrected; the defect is recorded in the
notebook entry because an in-place edit leaves no trace that it was ever wrong.

**A round-trip test cannot pin the direction.** Projecting and unprojecting with
the same matrix is exact under any invertible convention, including a transposed
one. Pinning `R_rect` requires an *external* anchor; the principal-row assertion
is that anchor. This is why step 5 ships both tests and not only the round trip.

**Sagittal gaze hides every error here.** At `elevation_down == 0`,
`R_rect = I`, so applying, omitting, or transposing it are bit-identical. Every
test of this decision therefore uses `el ≠ 0` *and* `az ≠ 0`. At `el = 0.4` a
transposed `R_rect` moves the fixation point 824 px off the principal row; at
`el = 0` it moves it not at all.

**The rectified frame is not gaze-centred.** Consumers that want the fovea at the
image centre must not assume this frame provides it; at `az ≠ 0` the fixation
point sits on the centre row but off the centre column.

## Verification

`tests/unit/test_oculomotor.py`:

- `test_rectification_rotation_matches_helmholtz_with_azimuth_zeroed` — pins the
  member and the naming against a test-local independent reimplementation.
- `test_rectification_puts_the_plane_of_regard_on_the_principal_row` — pins the
  selection criterion; the only test that distinguishes this member from the rest
  of the family.
- `test_rectification_rotation_is_sufficient_for_rectification` — `d_v` exactly
  zero in the induced pair, masked per ADR-0002 (validity is eye-indexed).
- `test_rectification_rotation_ignores_azimuth_and_vergence` — the structural
  independence, over a sweep.
- `test_transposing_the_rectifier_breaks_the_round_trip` — faults the module
  itself and requires the failure to be visible.
