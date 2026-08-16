"""Console entry point (``astereo``). Thin: parses args, delegates to experiments."""

from __future__ import annotations

import argparse
import sys

from activestereo import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="astereo", description="active-stereo toolkit")
    parser.add_argument("--version", action="version", version=f"activestereo {__version__}")
    sub = parser.add_subparsers(dest="command")

    info = sub.add_parser("info", help="print environment and layer inventory")
    info.set_defaults(func=_cmd_info)

    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 1
    return int(args.func(args))


def _cmd_info(_: argparse.Namespace) -> int:
    import numpy as np

    layers = ["geometry", "encoding", "inference", "scaling", "control", "policy"]
    print(f"activestereo {__version__}  (numpy {np.__version__})")
    for i, name in enumerate(layers, start=1):
        print(f"  L{i}  {name}")

    # Capability report, so "which version am I running?" has a one-line answer.
    # Every stale-checkout confusion in this project has been a config or module
    # file lagging behind, which is invisible until something fails oddly.
    print("\ncapabilities:")
    for label, ok in _capabilities().items():
        print(f"  {'yes' if ok else 'no ':4s} {label}")
    return 0


def _capabilities() -> dict[str, bool]:
    caps: dict[str, bool] = {}

    from activestereo.scenes import blender

    caps["multi-layer EXR render loading (ADR-0010)"] = hasattr(blender, "read_multilayer_exr")
    for label, module in (
        ("OpenImageIO (blender extra)", "OpenImageIO"),
        ("OpenCV (cv extra)", "cv2"),
        ("matplotlib (viz extra)", "matplotlib"),
    ):
        try:
            __import__(module)
            caps[label] = True
        except ImportError:
            caps[label] = False
    return caps


if __name__ == "__main__":
    sys.exit(main())
