# 2026-08-16 — Appearance-controlled Blender stimuli, and exp003

**Status:** `material-chart` stimulus landed, 108 tests green, exp003 run once —
both hypotheses falsified, and the useful result was neither of them.

## What happened

Built a rendered stimulus family in which surface appearance is a *controlled*
variable: eight coplanar patches spanning dense albedo texture to constant
albedo, matte to glossy, under three procedural lighting rigs, with geometry
bit-identical across every condition so ground-truth depth and occlusion cancel
exactly. Wired it through a `BlenderRenderScene` satisfying the `Scene` protocol,
and ran exp003 (issue #4) on 12 renders.

Appearance ground truth comes from render passes rather than the beauty image —
`Diffuse Color` for albedo, `Glossy Direct` for specular energy, `Material Index`
for the condition label. Measuring texture from the rendered image would conflate
albedo variation with shading gradient, which under a raking light are very
different things.

## The result, and the correction that produced it

Both hypotheses fell. H1 (matchers decline gracefully as texture vanishes) was
falsified hard: error on *answered* pixels rose 100× (block) and 455× (sgbm) from
dense to constant albedo, against a ≥2× falsifier. H2 (specularity degrades
matching at matched texture contrast) showed no effect at all on the patch
median.

I then wrote in findings.md that the matcher's variance "has no idea" the
textureless answers are wrong — reasoning by analogy from exp001's occlusion
result. **That was asserted, not measured, and measuring it inverted the
conclusion:**

| region | reported disparity variance | vs textured |
|---|---|---|
| textured, matched | 90 px² | 1× |
| textureless, matched | 57,340 px² | 637× |
| half-occluded | 426 px² | 5× |

Texture loss *is* flagged — 637× variance inflation against ~100× error
inflation, so L4's inverse-variance fusion discounts it more than adequately.
Half-occlusion is not: 5× is nowhere near enough for a fabricated measurement.
So the framework's real exposure is occlusion, not texture loss, and exp001's
finding is corroborated on a completely different stimulus class.

The lesson worth keeping is procedural: I nearly shipped a plausible,
theory-consistent claim about the uncertainty machinery that was backwards.
The only thing that caught it was measuring a number I had already written down.

## Wrong predictions, recorded

- **"Render noise will contaminate the textureless condition."** Flagged as the
  headline threat before running, on sound reasoning: a constant-albedo patch
  carries independently-drawn per-eye sampling noise. Tested it by re-rendering
  at 4096 spp against 512 spp — an 8× increase that should shrink noise 2.8×.
  Nothing moved (coverage 0.726 → 0.737, error 0.0561 → 0.0555). The residual
  0.3%-amplitude structure is deterministic shading. Threat refuted; finding
  strengthened.
- **A four-rung texture ladder.** It is effectively two rungs. Albedo contrast
  0.193 / 0.175 / 0.072 are statistically indistinguishable (coverage
  0.995/0.993/0.990); only 0.000 collapses. The entire transition lives between
  0.00 and 0.07, where there are no samples. Three of four rungs bought nothing.
- **Testing H2 with a patch median.** The specular effect is real but confined to
  the tail: above mismatch ≈0.38 (top 5% of pixels) median error rises 2–3× and
  p90 rises **14×** (0.005 → 0.07 m). Overall Spearman is −0.004. Wrong
  instrument, not absent phenomenon.
- **A monotonicity falsifier with no noise floor.** H1a "fails" for sgbm on a
  0.0011 coverage inversion. Substantively meaningless; reported as the
  pre-registered criterion computes it rather than rewritten after the fact.

## Five things the renders found that reading could not

Every one of these was caught by exercising the API rather than trusting it,
which is ADR-0009's standing lesson:

| Symptom | Cause |
|---|---|
| Layer lookup found nothing | Blender writes `Diffuse Color`, `Glossy Direct`, `Material Index` — with spaces, not `DiffCol`/`GlossDir`/`IndexMA` |
| `infer_depth_convention` said "radial" on a planar build | **Mine.** It assumes a flat calibration wall; any scene with nearer objects mid-frame satisfies "grows toward the corners" for the wrong reason. Now guarded by a radial-symmetry check |
| Texture ladder non-monotonic | **Mine.** Noise Scale is in bounding-box units; scale 90 across a 106 px patch is a 1.2 px period, below Nyquist, antialiased away — "dense" rendered *smoother* than "mid" |
| Disparity ran −3.6 to +10.2 px | **Mine.** Default `--convergence 1.4` put the fixation plane *inside* the scene. The repo learned this once already (2026-08-15 entry); nothing enforced it. Now `check_fixation_clears_scene` refuses |
| `grazing` rig unusable | **Mine.** Lamp beside the patch plane blew the backdrop to white and crushed the patches — measuring exposure, not shading. Moved forward so inverse-square dims the backdrop 3.2× |

The `depth_is_radial` hole is worth naming separately: `rig.json` writes it as
`null` because the render script genuinely cannot tell, and the consumer did
`bool(meta.get("depth_is_radial"))` — turning "nobody has checked" into "planar,
definitely" with no warning. `BlenderRenderScene` now measures it against the
chart's known-flat backdrop, and raises when it cannot.

## Next

- exp004: why does occlusion variance stay low, and does a cheap left-right
  consistency term fix it? That is where the exposure is.
- Re-test specularity on the p90 with sharper, larger highlights.
- Re-space the texture ladder geometrically inside [0, 0.07].
- Move `_boxsum` to `utils/` — three copies now (`inference/block.py`,
  `encoding/energy.py`, `scenes/blender.py`).
