### High-level plan

Five phases, each ending in a registered experiment. The ordering rule is *measure before repair*, so each repair is motivated by a number rather than by an argument.

**Phase A — Make fixation representable.** Split `StereoRig` (anatomy: baseline, focal length, principal point — fixed hardware) from a new `Fixation` type (oculomotor state: gaze direction and vergence). Add a `RefixableScene` Protocol whose `render` takes both. RDS implements it; Blender implements it next; Middlebury explicitly does *not*, and encoding that refusal in the type system is honest — a fixed photograph cannot be re-fixated, and the framework should be unable to pretend otherwise. Then rewrite the loop so it actually closes: fixate → re-render → L2/L3 → L4 → update a belief that persists across fixations → recompute saliency → next fixation. The persistent belief matters; active inference integrates evidence across fixations rather than discarding it, and there is currently nowhere for that state to live.

**Phase B — exp008: measure the loop as built.** First experiment ever to exercise L5/L6. The hypothesis comes free from exp004 and exp006, and it's falsifiable: *a variance-driven gaze policy under-samples half-occlusions relative to a uniform policy* — the anti-calibration predicts the controller is blind to exactly the geometry it should be investigating. Register the falsifier before running. If it survives, your two prior findings have a behavioural consequence, which is a much stronger claim than either made alone.

**Phase C — exp009: repair the confidence channel.** A `Confidence` Protocol beside `Estimate`, with left–right consistency, peak-ratio, and the incumbent curvature variance as three instantiations. Score by sparsification-curve AUC against the oracle, which is the comparable number in that literature and measures precisely the property L4 and L6 consume. This also fixes SGBM's constant variance as a side effect, closing the fairness complaint that exp001 and the CHANGELOG have both been carrying.

**Phase D — exp010: the active benchmark.** Error versus fixation budget, three arms — calibrated-confidence policy, raw-variance policy, uniform/raster baseline. This is the experiment that Middlebury structurally cannot express and that the framework exists to make. It's also where the XR design objectives finally have something to attach to.

**Phase E — geometry consolidation.** ADR-0007's off-axis/Vieth–Müller divergence, and the vertical-disparity blindness exp007 measured (dyavg up to ~0.5 px at Q, ignored by every matcher by construction). Phase A forces part of this anyway, since a gaze-direction type makes you commit to what "pointing the eyes" means geometrically.

Expect Phase A to break the demo's current numbers. That's a real cost and worth naming: something that presently runs and prints plausible output will stop doing so, and the honest reading is that it was printing plausible output for a loop that wasn't running.

