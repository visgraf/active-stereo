"""List every part, channel, and value range in a rendered EXR.

Blender writes multi-layer EXR as a multi-part file -- one part per pass. A
reader that stops at part 0 sees the beauty pass and reports no depth at all,
with nothing to indicate a layer was missed. This walks every part.

The decisive diagnostic when depth looks wrong: it says exactly which layers
Blender wrote and what is in them, rather than leaving us to infer it.

    python scripts/inspect_exr.py /tmp/calib/left.exr
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if not args:
        print(__doc__)
        return 1

    try:
        import OpenImageIO
    except ImportError:
        print("needs OpenImageIO: pip install -e '.[blender]'", file=sys.stderr)
        return 1

    for name in args:
        path = Path(name)
        src = OpenImageIO.ImageInput.open(str(path))
        if src is None:
            print(f"{path}: could not open ({OpenImageIO.geterror()})")
            continue

        print(f"\n{path}")
        index = 0
        try:
            while True:
                spec = src.spec()
                # First two arguments are subimage and miplevel: passing 0 while
                # positioned on a later part re-seeks to part 0 and segfaults.
                pixels = src.read_image(index, 0, 0, spec.nchannels, "float")
                data = np.asarray(pixels, dtype=float).reshape(
                    spec.height, spec.width, spec.nchannels
                )
                part = spec.get_string_attribute("name") or "(unnamed)"
                print(f"  part {index}: {part}  {spec.width}x{spec.height}")
                for i, channel in enumerate(spec.channelnames):
                    band = data[..., i]
                    finite = band[np.isfinite(band)]
                    if finite.size == 0:
                        print(f"      {channel:28s} all non-finite")
                        continue
                    print(
                        f"      {channel:28s} min={finite.min():12.4g}  "
                        f"max={finite.max():12.4g}  median={np.median(finite):12.4g}"
                    )
                index += 1
                if not src.seek_subimage(index, 0):
                    break
        finally:
            src.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
