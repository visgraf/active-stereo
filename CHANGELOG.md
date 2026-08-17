# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Tags mark milestones and submissions, so the paper can cite a fixed state.

## [Unreleased]

### Added
- `--scene material-chart` in `scripts/render_stereo.py`: eight coplanar patches
  spanning dense albedo texture to constant albedo, matte to glossy, under three
  procedural lighting rigs. Geometry is bit-identical across conditions, so
  appearance is the only variable; material-to-position assignment is permuted so
  texture level is not confounded with eccentricity
- Appearance ground truth from render passes — `Diffuse Color`, `Glossy Direct`,
  `Material Index` — read by `read_multilayer_exr`, with `albedo_texture_contrast`
  and `AppearanceGroundTruth.specular_mismatch`
- `BlenderRenderScene`: a render directory presented as a `Scene`. Refuses a
  mismatched rig rather than silently rescaling depth, and resolves the depth
  convention by measuring it against the chart's known-flat backdrop
- `scripts/render_chart_sweep.py`: renders the 12-condition exp003 stimulus set
- exp003 (issue #4): both hypotheses falsified. Texture loss is reported honestly
  (637x variance inflation) while half-occlusion is not (5x) — so occlusion is the
  more dangerous failure, corroborating exp001 on a rendered stimulus
- `scenes` package (ADR-0006): random-dot stereogram synthesis with z-buffer
  half-occlusion, four ground-truth depth maps, and a Blender render loader
- `scripts/render_stereo.py`: Blender stereo rendering with per-eye depth passes
- `scripts/demo_active_stereo.py`: end-to-end six-layer demo, successor to the
  prototype's `active_stereo_demo.py`
- `StereoStimulus` carrying `matched` and `in_frame` as separate masks
- ADR-0007: off-axis rendering, and the disclosure that L1 models a
  shifted-frustum rig rather than the Vieth-Muller horopter
- `tests/integration/`: end-to-end pipeline tests on RDS stimuli
- Six-layer package structure (`geometry`, `encoding`, `inference`, `scaling`,
  `control`, `policy`) with Protocol-based extension points (ADR-0004)
- `Estimate` type carrying value and variance (ADR-0005)
- `RunContext`: run-ids pinned to git SHA, seed, and config
- Five seed ADRs; three backed by regression tests
- CI: tests on 3.10/3.12, lint, types, and a separate ADR-regression job
- `CLAUDE.md` constitution, scoped permissions, four custom commands

### Changed
- Python floor raised to 3.12; CI matrix now 3.12 / 3.14; `mypy src` is a
  blocking CI step (ADR-0008)

### Fixed
- `infer_depth_convention` answered `"radial"` with full confidence on any scene
  that was not a fronto-parallel calibration wall — nearer objects mid-frame make
  depth "grow toward the corners" for the wrong reason. Now guarded by a
  radial-symmetry check that returns `"unknown"` instead
- `rig.json` writes `depth_is_radial: null` because the render script cannot know
  it, and the consumer did `bool(meta.get(...))` — turning "nobody has checked"
  into "planar, definitely" silently. An uncorrected radial pass is a few percent
  of peripheral depth error, indistinguishable from an ADR-0003 result
- `demo_active_stereo.py` scored occlusion as `~stim.matched`, conflating
  half-occlusion with out-of-frame and inflating the statistic with border pixels
- `[tool.mypy] python_version = "3.10"` made mypy parse numpy's PEP 695 stubs
  with an old grammar, aborting the type check before it reached our code
- SGBM now calls `cv2.StereoSGBM.create` rather than the module-level
  `StereoSGBM_create` alias, which is missing from OpenCV's bundled stubs
- `matched` conflated half-occlusion with out-of-frame correspondents, making
  smooth unoccluded surfaces report a border band of false occlusion
- Parabolic subpixel fit produced variance 0 alongside a `nan` location when a
  neighbouring cost was infinite — a maximally confident non-answer
- Eccentricity normalisation was off by half a pixel, making the ADR-0003
  penalty resolution-dependent at the 3% level

### Known issues
- L1's projection is off-axis (planar horopter) while `horopter.py` computes the
  Vieth-Muller circle (toed-in). They diverge with eccentricity. See ADR-0007.
- SGBM reports a constant variance, not a posterior width, so cross-matcher
  fusion comparisons at L4 are not yet fair.

### Migration status
- `encoding`: Protocol only; energy model already migrated
- `inference`: block matching and SGBM; MRF belief propagation pending
- `scenes`: RDS and Blender loader landed; Blender depth-pass convention needs
  one calibration render per Blender version
