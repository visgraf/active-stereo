"""Report what a Middlebury 2014 scene directory actually contains.

The analogue of ``inspect_exr.py``, and it exists for the same reason: none of
the conventions this corpus depends on are documented on Middlebury's public
pages. Row order, the encoding of unknown disparities, whether the calibration
maps onto our rig at all -- every one of them is established by measurement, and
a loader written against an assumption instead is wrong in a way that looks
entirely plausible downstream.

    python scripts/inspect_middlebury.py ~/datasets/middlebury2014/Adirondack-perfect

Run this before trusting any number out of a new scene. The two lines to read
first are the row-order verdict and the GT noise floor.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from activestereo.scenes.middlebury import (
    pfm_header,
    read_calib,
    read_pfm,
    rig_from_calib,
)


def describe(path: Path) -> None:
    print(f"\n{'=' * 78}\n{path.name}\n{'=' * 78}")

    present = sorted(p.name for p in path.iterdir()) if path.is_dir() else []
    print(f"\nfiles: {', '.join(present)}")

    calib_path = path / "calib.txt"
    if not calib_path.exists():
        print("\n  no calib.txt -- not a Middlebury 2014 scene directory")
        return

    calib = read_calib(calib_path)
    rig = rig_from_calib(calib)

    print("\ncalibration")
    for key in ("width", "height", "ndisp", "isint", "vmin", "vmax", "dyavg", "dymax"):
        if key in calib:
            print(f"  {key:10s} {calib[key]}")
    print(f"  {'f':10s} {calib['f']:.3f} px")
    print(f"  {'doffs':10s} {calib['doffs']:.3f} px")
    print(f"  {'baseline':10s} {calib['baseline']:.3f} mm")

    print("\ncalib -> StereoRig  (doffs is the whole of the mapping)")
    print(f"  focal_px        {rig.focal_px:.3f}")
    print(f"  baseline        {rig.baseline:.6f} m")
    print(f"  principal_point {rig.principal_point}  (row, col)")
    print(f"  vergence        {rig.vergence:.6f} rad  ({np.rad2deg(rig.vergence):.3f} deg)")
    print(f"  fixation        {rig.fixation_distance:.4f} m")

    if calib.get("dymax", 0.0) > 0.0:
        print(
            f"\n  ** dymax = {calib['dymax']} px of VERTICAL disparity. Every matcher in\n"
            "     inference/ assumes epipolar lines are image rows. This is an\n"
            "     -imperfect scene and is out of scope."
        )

    for name in ("disp0.pfm", "disp1.pfm", "disp0-sd.pfm"):
        pfm = path / name
        if not pfm.exists():
            continue
        magic, width, height, scale = pfm_header(pfm)
        data = read_pfm(pfm)
        finite = np.isfinite(data)
        print(f"\n{name}")
        print(
            f"  header    {magic} {width}x{height} scale={scale}"
            f"  ({'little' if scale < 0 else 'big'}-endian)"
        )
        print(
            f"  unknown   {(~finite).sum()} px ({100.0 * (~finite).mean():.2f}%)"
            f"   [inf={np.isinf(data).sum()} nan={np.isnan(data).sum()}]"
        )
        if finite.any():
            lo, hi = data[finite].min(), data[finite].max()
            print(f"  range     [{lo:.3f}, {hi:.3f}]  median={np.median(data[finite]):.3f}")

        if name == "disp0.pfm":
            _row_order(path, data)
            _bounds(calib, data, finite)
            _depth(calib, data, finite)
        if name == "disp0-sd.pfm" and finite.any():
            floor = float(np.median(data[finite]))
            print(
                f"\n  GT NOISE FLOOR: median {floor:.4f} px of disparity uncertainty.\n"
                "  A residual below this is not a finding, it is the scanner."
            )


def _row_order(path: Path, disp: np.ndarray) -> None:
    """PFM stores rows bottom-up; ``read_pfm`` flips. Show the evidence, not the claim.

    Skipping the flip gives a vertically mirrored ground truth whose statistics
    are entirely plausible, so this is worth asserting against the image rather
    than against the spec.
    """
    top = disp[: disp.shape[0] // 4]
    bottom = disp[-disp.shape[0] // 4 :]
    med_top = float(np.nanmedian(np.where(np.isfinite(top), top, np.nan)))
    med_bottom = float(np.nanmedian(np.where(np.isfinite(bottom), bottom, np.nan)))
    print(
        f"\n  row order (after flip)  top quarter median {med_top:.1f} px"
        f" | bottom quarter median {med_bottom:.1f} px"
    )
    verdict = "nearer at bottom" if med_bottom > med_top else "nearer at top"
    print(f"    -> {verdict}. Compare against im0.png by eye; a table-top scene is")
    print("       nearer at the bottom, and the opposite means the flip is wrong.")


def _bounds(calib: dict, disp: np.ndarray, finite: np.ndarray) -> None:
    ndisp = calib.get("ndisp")
    if ndisp is None or not finite.any():
        return
    lo, hi = float(disp[finite].min()), float(disp[finite].max())
    inside = lo >= 0.0 and hi < ndisp
    print(f"\n  search range: disparities in [{lo:.1f}, {hi:.1f}], ndisp={ndisp} -> ", end="")
    print("inside" if inside else "** OUTSIDE [0, ndisp) **")
    vmin, vmax = calib.get("vmin"), calib.get("vmax")
    if vmin is not None and vmax is not None:
        print(f"  published vmin/vmax {vmin}/{vmax} vs measured {lo:.1f}/{hi:.1f}")
    print(
        f"  BlockMatcher(max_disparity={ndisp}) -- not ndisp-1: it rejects best==D-1,\n"
        "  so an off-by-one silently discards every true maximum-disparity pixel."
    )


def _depth(calib: dict, disp: np.ndarray, finite: np.ndarray) -> None:
    """Middlebury's own formula, in metres. Deliberately not via L1.

    ADR-0006 forbids the stimulus and the estimator sharing a code path. This is
    the stimulus side, so it is written out longhand here and in the loader.
    """
    if not finite.any():
        return
    fb = calib["f"] * calib["baseline"]
    near = fb / (float(disp[finite].max()) + calib["doffs"]) / 1000.0
    far = fb / (float(disp[finite].min()) + calib["doffs"]) / 1000.0
    print(f"\n  depth  Z = f*b/(d + doffs):  [{near:.3f}, {far:.3f}] m")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("scenes", nargs="+", type=Path, help="scene directories")
    args = ap.parse_args(argv)

    for path in args.scenes:
        if not path.is_dir():
            print(f"{path}: not a directory", file=sys.stderr)
            continue
        describe(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
