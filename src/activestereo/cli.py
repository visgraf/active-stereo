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
    return 0


if __name__ == "__main__":
    sys.exit(main())
