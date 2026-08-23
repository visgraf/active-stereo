# 2026-08-23 — Demo oracle removal: the loop never listened to vergence anyway

Branch `fix/demo-remove-oracle`, migration step 9
(`docs/plans/fixation-migration.md`). `active_loop` in
`scripts/demo_active_stereo.py` measured vergence from
`Estimate(stim.disparity, 0.25)` — ground truth with a fabricated constant
variance — while the real L3 estimate sat unused in `main()`. The change
passes the L3 estimate in; nothing else. The loop stays open (saliency
computed once outside the loop, no re-render, the Kalman state feeds
nothing — steps 8 and 11).

Both runs: `python scripts/demo_active_stereo.py --scene disk --matcher
block --seed 0` (all other flags at defaults: 240×320, d_max 48, window 7,
fixation distance 2.5 m, 20-fixation budget).

- **Before** (oracle): run `demo-20260823T204941-4cdc575`, SHA `4cdc575`.
- **After** (L3): run `demo-20260823T205301-d3facd1`, SHA `d3facd1`.

## What I expected

Everything downstream of the vergence measurement to get worse: the previous
numbers were produced by reading the answer with a made-up 0.25 px² variance.

## What happened

**The fixation trace is identical, element for element** — all 20 fixations,
same order. This is not luck; it is provable from the code: `next_fixation`
consumes only the saliency map (computed once from L4 depth, outside the
loop) and the visited list. The vergence branch is a dead end — the Kalman
state feeds nothing. So the oracle was never load-bearing for the loop's
*behaviour*, only for its *reported numbers*. The demo's fixation pattern was
honest all along; its vergence telemetry was fiction.

What did change, all of it in the telemetry:

- **Measurement refusals: 0 → 7 of 20.** The first seven fixations all land
  on the left image border (column 0–1), where the block matcher has no
  valid disparities and `estimate_vergence_disparity` correctly refuses
  (< 25 % of the window valid). The oracle happily "measured" ground truth
  there. The Kalman filter predicts through all seven refusals holding its
  prior, 1.4667° — exactly the rig vergence, 2·arctan(0.064/5).
- **Vergence trajectory.** Before: jumps to 2.11° on the first fixation,
  settles at 2.329°. After: flat at the 1.4667° prior for seven iterations,
  then climbs 1.47° → 2.27° over the 13 usable measurements. Final estimates
  end 0.06° apart (2.268° vs 2.329°).
- **Final vergence variance: 2.2e-4 → 2.8e-3 rad².** An order of magnitude
  less confident, which is the honest number — the fabricated 0.25 px² had
  been laundered through the median-window estimator into false precision.
- **Termination: unchanged.** Both runs hit the 20-fixation budget;
  neither terminates naturally. Per ADR-0002 the cap is not convergence —
  but this is the budget-limit case (inhibition of return guarantees no
  repeats; candidates remained), not the hang, and it is a property of the
  saliency threshold, which the vergence input cannot reach.

## What I conclude

The headline "expect it to get worse" resolves as: the *estimates* got
honestly worse (slower, 12× less certain), but no behaviour changed, because
the loop is structurally insensitive to its vergence input. Two findings
worth having before exp008:

1. **Any vergence-estimator comparison run through this demo is void until
   steps 8/11 close the loop.** The trajectory, termination, and metrics
   blocks are identical under a ground-truth oracle and the real matcher;
   only the trace differs. exp008 must not use the open-loop demo as its
   harness.
2. **Saliency concentrates fixations exactly where measurement fails.**
   Uncertainty saliency sent 7 of 20 fixations to border regions the matcher
   refuses. Once the loop closes and fixations drive re-rendering, the
   refusal path (`(nan, inf)` → Kalman predict-through) will be exercised
   heavily, not occasionally. It behaved correctly here — 35 % refusals,
   no wall-drive — which is the first real exercise of the
   `estimate_vergence_disparity` refusal contract outside its unit tests.

Full per-iteration traces are in each run's `summary.json` under the run-ids
above.
