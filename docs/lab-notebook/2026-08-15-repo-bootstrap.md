# 2026-08-15 — Repository bootstrap

**Git SHA:** (initial commit)
**Status:** scaffold complete, 42 tests green

## What happened

Migrated from the single-script prototype (`active_stereo_demo.py`) to a layered
package. The six framework layers became the module boundaries (ADR-0004), and
the three closures became enforced invariants documented in CLAUDE.md §3.

Seeded five ADRs. Three of them (0001–0003) record lessons already paid for in
the prototype; each now has a regression test that would have caught the original
failure.

## Bugs found while writing the tests

Writing the regression tests immediately surfaced three real defects that the
prototype had masked:

1. **Subpixel fit on infinite costs.** When a neighbouring cost was `inf`, the
   parabolic fit produced variance `0` (infinite curvature) alongside a `nan`
   location — a maximally confident non-answer that would have entered fusion
   with infinite weight. Now rejected explicitly.
2. **Test fixture had the shift convention backwards.** The synthetic pair was
   built as `left[x] = base[x+d]`, `right[x] = base[x]`, which is off by `2d`
   from the matcher's `left[x] ≈ right[x-d]` convention. Worth noting: this is a
   *test* bug, and it would have silently validated a wrong matcher.
3. **Eccentricity normalisation off by half a pixel.** Normalising by
   `0.5*hypot(H, W)` instead of the centre-to-corner-pixel distance made the
   penalty resolution-dependent at the 3% level, defeating the purpose of
   normalising at all.

None of these were visible from reading the code.

## Next

- Migrate the binocular energy model into `encoding/` against the existing Protocol.
- Migrate MRF belief propagation into `inference/`; replace the curvature-proxy
  variance with a real posterior width. That unblocks the deferred alternative in
  ADR-0001 (confidence-weighted vergence).
- Wire the Blender render scripts into `scripts/` with config-driven scenes.
- Calibrate the ADR-0003 coefficient `c` against a scene with ground-truth depth.
