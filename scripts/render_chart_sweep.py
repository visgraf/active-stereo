"""Render the exp003 material-chart condition set: lighting x permutation.

Runs *outside* Blender and invokes it once per condition, unlike
``render_stereo.py`` which runs inside it. Kept separate for that reason: this
one may import from the project environment, that one may not.

Usage
-----
    python scripts/render_chart_sweep.py --out results/stimuli/chart

Renders go to ``results/`` because ``data/`` holds pointers and never blobs
(CLAUDE.md section 2), and because ``results/`` is git-ignored. They are
stimuli rather than run-addressed artefacts, so they sit in their own subtree
and the experiment records the path it read.

The permutation sweep is not optional decoration. Fixing the material-to-patch
assignment would confound texture level with eccentricity, which is the variable
ADR-0003 makes the whole pipeline sensitive to.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

LIGHTING = ("ambient", "key", "grazing")
PERMUTATIONS = (0, 1, 2, 3)


def condition_name(lighting: str, permutation: int) -> str:
    return f"{lighting}_p{permutation}"


def render_one(
    blender: str, out: Path, config: Path, lighting: str, permutation: int, samples: int
) -> bool:
    cmd = [
        blender,
        "--background",
        "--factory-startup",
        "--python",
        "scripts/render_stereo.py",
        "--",
        "--out",
        str(out),
        "--config",
        str(config),
        "--scene",
        "material-chart",
        "--lighting",
        lighting,
        "--permutation",
        str(permutation),
        "--samples",
        str(samples),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    ok = (out / "left.exr").exists() and (out / "right.exr").exists()
    if not ok:
        print(result.stdout[-2000:], file=sys.stderr)
        print(result.stderr[-2000:], file=sys.stderr)
    return ok


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, default=Path("results/stimuli/chart"))
    p.add_argument("--config", type=Path, default=Path("configs/scene/blender_material_chart.json"))
    p.add_argument("--blender", default=shutil.which("blender") or "blender")
    p.add_argument("--samples", type=int, default=512)
    p.add_argument("--force", action="store_true", help="re-render conditions already present")
    args = p.parse_args()

    if shutil.which(args.blender) is None and not Path(args.blender).exists():
        raise SystemExit(
            f"blender not found at {args.blender!r}. Pass --blender /path/to/blender. "
            "This script cannot substitute anything for it: the stimuli are the "
            "experiment."
        )

    failures = []
    for lighting in LIGHTING:
        for permutation in PERMUTATIONS:
            out = args.out / condition_name(lighting, permutation)
            if (out / "left.exr").exists() and not args.force:
                print(f"[sweep] have {out}")
                continue
            out.mkdir(parents=True, exist_ok=True)
            print(f"[sweep] rendering {out} ...", flush=True)
            if not render_one(args.blender, out, args.config, lighting, permutation, args.samples):
                failures.append(str(out))
                print(f"[sweep] FAILED {out}", file=sys.stderr)

    total = len(LIGHTING) * len(PERMUTATIONS)
    print(f"[sweep] {total - len(failures)}/{total} conditions present in {args.out}")
    if failures:
        # A partial stimulus set silently unbalances the design: a missing
        # permutation reintroduces exactly the eccentricity confound the sweep
        # exists to remove.
        raise SystemExit(f"[sweep] {len(failures)} condition(s) failed: {failures}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
