# 2026-08-23 — L1 vs L2 at project scales: the k choice is material

Branch `feat/eye-rotations`, migration step 3
(`docs/plans/fixation-migration.md`). ADR-0014 deliberately left one number
unrecorded — the L1-vs-L2 vertical displacement at the project's actual
stimulus scales — because the hand-derived estimate that existed was
unverified arithmetic. This entry records the computed number, from the
`eye_rotations` implementation committed here (the recompute script imported
`activestereo.geometry`; it did not re-derive the construction).

Setup: project rig (b = 0.064 m, f = 800 px, 240×320), gaze at image-edge
eccentricity (azimuth 0.197 rad ≈ 11.3°, elevation ±0.149 rad ≈ 8.5°),
fixation depths at the three in-repo working scales: 1.0 m
(`configs/default.yaml`, vergence 3.67°), 0.7 m (the demo disk), 0.4 m (the
near limit of `depth_range`). Torsion τ is the signed twist about the gaze
relative to the strict-Listing (k = 0) orientation, so τ(k=0) ≡ 0 — confirmed
exactly (0.0e+00) in every case.

## Exact torsion, k = 0.25 vs k = 0

| fixation depth | μ (rad) | τ per eye (rad) | Δτ between eyes (rad) |
|---|---|---|---|
| 1.0 m | 0.0640 | ±1.179e-3 / ∓1.185e-3 | 2.364e-3 |
| 0.7 m | 0.0914 | ±1.682e-3 / ∓1.694e-3 | 3.375e-3 |
| 0.4 m | 0.1597 | ±2.930e-3 / ∓2.966e-3 | 5.896e-3 |

Signs: upward proximal gaze intorts both eyes (τ_L > 0, τ_R < 0 in the
head-frame twist convention), downward extorts, opposite between the eyes —
ADR-0014's observable, pinned by `test_elevation_dependent_torsion_signs`.

## Vertical pixel displacement — FIRST-ORDER ONLY

δy ≈ x·Δτ at horizontal offset x = 160 px (image edge). **These are
first-order estimates, not computed projections**; the exact figure requires
step 4's toed-in projection and will be computed there.

| fixation depth | per-eye δy | differential δy (the matching-relevant one) |
|---|---|---|
| 1.0 m | ≈ 0.19 px | **≈ 0.38 px** |
| 0.7 m | ≈ 0.27 px | **≈ 0.54 px** |
| 0.4 m | ≈ 0.47 px | **≈ 0.94 px** |

## Benchmark against measured in-repo scales

- exp007 (`findings.md:50`): MiddEval3 `dyavg` up to ≈ 0.5 px at Q. The
  L1-vs-L2 differential displacement at the demo's own working distances is
  the **same order as real rectification error on MiddEval3**.
- exp006 (`findings.md:47–48`): median |Δd| on RDS is 0.0714 px for the block
  matcher and 0.0074 px for the selected energy bank. (ADR-0014's "≈ 0.07 px
  best-case RDS" matches the block matcher; the bank's best case is 10×
  lower — both cited here so the comparison is honest.) The L1-vs-L2
  displacement is **5–13× the block matcher's best-case median** and two to
  three orders above the bank's.

Conclusion: the choice of k is material at project scales — getting it wrong
injects vertical disparity comparable to MiddEval3's measured rectification
error and well above matcher precision. This is what makes ADR-0014's k-sweep
worth running, and why it doubles as an implementation audit.

## A numeric coincidence, disarmed

The static torsion above fits τ ≈ k·μ·el/2 at first order. The /2 is the
spherical excess of the ẑ–p_e–g_e triangle — a geometric consequence of
composing shortest arcs. It is **unrelated to the Tweed–Vilis half-angle
rule**, which concerns the angular-*velocity* axis during movements and tilts
by half the *eccentricity*; nothing velocity-domain enters `eye_rotations`,
which computes static orientations. Recorded so the /2 never gets mislabelled
as the half-angle rule (the two are routinely conflated).

Provenance: a plan-stage scratch construction produced the same table; per
the handoff contract the recorded numbers are the ones recomputed from the
implementation in this commit. The earlier hand estimate from Chat was kept
out of ADR-0014 as unverified arithmetic and stays out of the record here;
only the computed values above are citable.
