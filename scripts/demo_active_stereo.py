"""End-to-end demonstration of the six-layer loop on a random-dot stereogram.

The successor to the prototype's ``active_stereo_demo.py``. Unlike the prototype
this is *orchestration only*: every computation lives in ``src/activestereo/``
and is covered by tests. If you find yourself adding an algorithm here, it
belongs in a layer.

Usage
-----
    python scripts/demo_active_stereo.py --scene disk --matcher block
    python scripts/demo_active_stereo.py --scene staircase --matcher sgbm --plot
    python scripts/demo_active_stereo.py --render data/scenes/office_01
    python scripts/demo_active_stereo.py --middlebury Motorcycle --matcher energy --plot
    python scripts/demo_active_stereo.py --middlebury Piano --right-variant im1E
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from activestereo.control import VergenceKalman, estimate_vergence_disparity
from activestereo.inference import BlockMatcher
from activestereo.policy import next_fixation, uncertainty_saliency
from activestereo.policy.foveation import confine_to_fovea
from activestereo.scaling import scale_to_depth
from activestereo.scenes import (
    RandomDotStereogram,
    StereoStimulus,
    corrugated,
    disk,
    slanted_plane,
    staircase,
)
from activestereo.types import Estimate, StereoRig
from activestereo.utils import RunContext

SCENES = {
    "disk": disk,
    "staircase": staircase,
    "slanted_plane": slanted_plane,
    "corrugated": corrugated,
}


def build_matcher(kind: str, max_disparity: int, window: int):
    if kind == "block":
        return BlockMatcher(max_disparity=max_disparity, window=window)
    if kind == "sgbm":
        from activestereo.inference.sgbm import SGBMMatcher

        return SGBMMatcher(max_disparity=max_disparity, block_size=window)
    if kind == "energy":
        from activestereo.encoding import MultiScaleEnergyEncoder
        from activestereo.inference import EnergyDecoder

        # exp006's registered selection (config stage_b.selected + readout;
        # run exp006a-20260820T233759-4ea8400). Validated on the Middlebury
        # corpus, not retuned here.
        encoder = MultiScaleEnergyEncoder(
            np.arange(0, max_disparity + 1, dtype=float),
            scales=((4, 2), (8, 4), (16, 8), (32, 16), (48, 24)),
            combine="product",
            floor=1e-3,
        )
        return EnergyDecoder(encoder=encoder, flatness=0.05, centroid_halfwidth=2)
    raise ValueError(f"unknown matcher: {kind}")


def evaluate(depth: Estimate, stim: StereoStimulus) -> dict[str, float]:
    """Score an estimate against ground truth, separating the two failure kinds.

    ``matched`` regions are where a correct matcher should succeed;
    ``occluded`` regions are where it should *decline*. Scoring them together
    hides the distinction and rewards a matcher that confidently hallucinates
    depth in half-occlusions.
    """
    err = np.abs(depth.value - stim.depth)
    got = np.isfinite(depth.value)

    on_matched = stim.matched & got
    # stim.occluded, not ~stim.matched. A pixel fails to match for two unrelated
    # reasons -- a nearer surface hid its partner (geometry) or the partner fell
    # off the sensor (a rig limit) -- and StereoStimulus keeps them separate for
    # exactly this reason. Pooling them counts every border pixel as a
    # hallucination, which inflates this number on any wide-field render.
    # exp001's runner has always done it correctly; this had drifted.
    occluded = stim.occluded
    return {
        "depth_mae_m": float(np.nanmedian(err[on_matched])) if on_matched.any() else float("nan"),
        "coverage_matched": float((stim.matched & got).sum() / max(stim.matched.sum(), 1)),
        "false_positive_occluded": float((occluded & got).sum() / max(occluded.sum(), 1)),
        "occlusion_fraction": stim.occlusion_fraction,
    }


def active_loop(
    depth: Estimate,
    stim: StereoStimulus,
    max_fixations: int,
    sigma: float,
    inhibition: float,
    dt: float,
) -> dict[str, object]:
    """Run L5/L6: choose fixations, track vergence, and stop when done.

    Termination is the observable that matters. A loop that runs to its iteration
    cap has not converged, it has been cut off -- see ADR-0002.
    """
    kf = VergenceKalman(dt=dt, initial_state=(stim.rig.vergence, 0.0))
    saliency = uncertainty_saliency(depth, sigma=sigma)
    visited: list[tuple[int, int]] = []
    trace = []

    for _ in range(max_fixations):
        target = next_fixation(saliency, visited=visited, inhibition_radius=inhibition)
        if target is None:
            break
        visited.append(target)

        d_hat, d_var = estimate_vergence_disparity(
            Estimate(stim.disparity, np.where(np.isfinite(stim.disparity), 0.25, np.nan)),
            centre=target,
        )
        angle_meas = (
            float(2.0 * np.arctan(stim.rig.baseline / (2.0 * _fixation_depth(d_hat, stim.rig))))
            if np.isfinite(d_hat)
            else float("nan")
        )
        kf.step(angle_meas, d_var if np.isfinite(d_var) else float("inf"))
        trace.append(
            {
                "fixation": target,
                "vergence_rad": kf.angle,
                "vergence_var": kf.angle_var,
                "measured": bool(np.isfinite(d_hat)),
            }
        )

    return {
        "n_fixations": len(visited),
        "terminated_naturally": len(visited) < max_fixations,
        "measurement_refusals": sum(1 for t in trace if not t["measured"]),
        "final_vergence_deg": float(np.rad2deg(kf.angle)),
        "trace": trace,
    }


def _fixation_depth(d_hat: float, rig: StereoRig) -> float:
    inv_fix = 0.0 if not np.isfinite(rig.fixation_distance) else 1.0 / rig.fixation_distance
    inv_Z = d_hat / (rig.focal_px * rig.baseline) + inv_fix
    return 1.0 / inv_Z if inv_Z > 0 else float("inf")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--scene", default="disk", choices=sorted(SCENES))
    p.add_argument("--render", type=Path, default=None, help="Blender render dir instead of RDS")
    p.add_argument(
        "--middlebury",
        default=None,
        help="Middlebury 2014 scene name (e.g. Motorcycle) or a scene directory",
    )
    p.add_argument("--matcher", default="block", choices=["block", "sgbm", "energy"])
    p.add_argument("--shape", type=int, nargs=2, default=[240, 320])
    # None means "resolve per source": scene.ndisp for Middlebury (the spread is
    # wide -- Shelves 80, Vintage 247 at downsample 3 -- and a fixed default
    # truncates the search range in a way that reads as matcher failure), 48 for
    # the RDS scenes (covers disk at 0.7 m). An explicit value always wins.
    p.add_argument("--max-disparity", type=int, default=None)
    p.add_argument(
        "--downsample",
        type=int,
        default=3,
        help="Middlebury only. Odd factors avoid a half-pixel offset (ADR-0012).",
    )
    p.add_argument(
        "--right-variant",
        default="im1",
        choices=["im1", "im1E", "im1L"],
        help="Middlebury only: im1E varies exposure, im1L lighting; geometry is fixed",
    )
    p.add_argument("--window", type=int, default=7)
    p.add_argument("--dot-size", type=int, default=2)
    p.add_argument("--noise", type=float, default=0.0)
    p.add_argument("--convergence", type=float, default=2.5, help="fixation distance, m")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--foveal-coefficient", type=float, default=1e-4)
    p.add_argument("--max-fixations", type=int, default=20)
    p.add_argument("--plot", action="store_true")
    args = p.parse_args()

    rng = np.random.default_rng(args.seed)
    shape = tuple(args.shape)
    max_disparity = args.max_disparity

    if args.middlebury is not None:
        from activestereo.scenes.middlebury import MiddleburyScene
        from activestereo.scenes.registry import data_root

        candidate = Path(args.middlebury)
        directory = candidate if candidate.is_dir() else data_root() / f"{args.middlebury}-perfect"
        if not directory.is_dir():
            raise SystemExit(
                f"not a Middlebury scene directory: {directory}\n"
                "Run: python scripts/fetch_middlebury.py"
            )
        scene = MiddleburyScene(directory, downsample=args.downsample)
        rig = scene.rig
        stim = scene.stimulus(args.right_variant)
        scene_name = scene.name
        if max_disparity is None:
            # ndisp, not ndisp - 1: BlockMatcher rejects a winner at the last
            # index of its search range (see MiddleburyScene.ndisp).
            max_disparity = scene.ndisp
    elif args.render is not None:
        from activestereo.scenes.blender import BlenderRenderScene

        # BlenderRenderScene resolves the rig and the depth convention from the
        # render itself. The previous code did
        # `depth_is_radial=bool(meta.get("depth_is_radial"))`, and rig.json
        # writes that field as null because the render script cannot know it --
        # so "nobody has calibrated this" silently became "planar, definitely".
        # An uncorrected radial pass is a few percent of peripheral depth error,
        # which is indistinguishable from an ADR-0003 result.
        scene = BlenderRenderScene(args.render)
        rig = scene.rig
        stim = scene.stimulus()
        scene_name = scene.name
    else:
        rig = StereoRig(
            baseline=0.064,
            focal_px=800.0,
            vergence=2 * np.arctan(0.064 / 2 / args.convergence),
        )
        scene = RandomDotStereogram(
            SCENES[args.scene],
            name=f"rds_{args.scene}",
            shape=shape,
            dot_size=args.dot_size,
            noise=args.noise,
        )
        stim = scene.render(rig, rng)
        scene_name = scene.name

    if max_disparity is None:
        max_disparity = 48  # covers disk at 0.7 m

    ctx = RunContext(
        tag="demo",
        seed=args.seed,
        config=vars(args) | {"scene": scene_name, "max_disparity": max_disparity},
    )

    matcher = build_matcher(args.matcher, max_disparity, args.window)
    disparity = matcher.match(stim.left, stim.right)  # L3
    depth = scale_to_depth(disparity, stim.rig)  # L4
    depth = confine_to_fovea(depth, coefficient=args.foveal_coefficient)  # L6 remainder

    metrics = evaluate(depth, stim)
    loop = active_loop(
        depth,
        stim,
        max_fixations=args.max_fixations,
        sigma=3.0,
        inhibition=20.0,
        dt=1 / 60,
    )

    summary = {
        "scene": scene_name,
        "matcher": matcher.name,
        "metrics": metrics,
        "active_loop": {k: v for k, v in loop.items() if k != "trace"},
    }
    ctx.path("summary.json").write_text(json.dumps(summary | {"trace": loop["trace"]}, indent=2))
    print(json.dumps(summary, indent=2))

    if args.plot:
        _plot(stim, disparity, depth, loop, ctx.path("demo.png"))
        print(f"figure: {ctx.path('demo.png')}")

    print(f"run-id: {ctx.run_id}")
    if not loop["terminated_naturally"]:
        print(
            "note: reached the fixation budget with candidates remaining. This is a "
            "budget limit, not the ADR-0002 hang -- inhibition of return guarantees "
            "no location repeats. Raise --max-fixations to explore further."
        )
    return 0


def _plot(stim, disparity, depth, loop, path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(2, 3, figsize=(13, 7))

    panels = [
        (ax[0, 0], stim.left, "gray", "left", False),
        (ax[0, 1], stim.right, "gray", "right", False),
        (ax[0, 2], stim.matched, "gray", "ground-truth matched", False),
        (ax[1, 0], stim.disparity, "viridis", "true disparity (px)", True),
        (ax[1, 1], disparity.value, "viridis", "estimated disparity (px)", True),
        (ax[1, 2], depth.variance, "magma", "posterior variance", True),
    ]
    for axis, data, cmap, title, bar in panels:
        im = axis.imshow(data, cmap=cmap)
        axis.set_title(title, fontsize=10)
        if bar:
            plt.colorbar(im, ax=axis, fraction=0.046)

    if loop["trace"]:
        r = [t["fixation"][0] for t in loop["trace"]]
        c = [t["fixation"][1] for t in loop["trace"]]
        ax[1, 2].plot(c, r, "o-", color="cyan", ms=4, lw=1)

    for a in ax.ravel():
        a.set_xticks([])
        a.set_yticks([])
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


if __name__ == "__main__":
    raise SystemExit(main())
