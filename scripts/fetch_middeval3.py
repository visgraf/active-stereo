"""Fetch the Middlebury Stereo Evaluation v3 (MiddEval3) distribution.

Blobs never enter the repository. They land in ``$ACTIVESTEREO_MIDDEVAL3_ROOT``
(default ``~/datasets/middeval3``), leaving ``data/`` for DVC pointers as
CLAUDE.md §2 requires.

    python scripts/fetch_middeval3.py --dry-run
    python scripts/fetch_middeval3.py --record-checksums     # first fetch
    python scripts/fetch_middeval3.py                        # verifies

The file list lives in ``configs/dataset/middeval3.yaml`` and is deliberately
not an argument. All four archives extract into one shared ``MiddEval3/``
tree -- that is the layout the SDK's own scripts expect, so the merge is the
point, not an accident.

Reuses the download/checksum/safe-extract machinery from
``fetch_middlebury.py`` rather than restating it; the two scripts differ only
in manifest shape (fixed file list here, per-scene list there).
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import zipfile
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_middlebury import _write_checksums, download, sha256

CONFIG = Path(__file__).resolve().parent.parent / "configs" / "dataset" / "middeval3.yaml"


def data_root() -> Path:
    """Where the MiddEval3 tree lives. Outside the repository, always."""
    return Path(os.environ.get("ACTIVESTEREO_MIDDEVAL3_ROOT", "~/datasets/middeval3")).expanduser()


def _safe_extract_merged(z: zipfile.ZipFile, root: Path) -> None:
    """Extract into ``root``, refusing escapes; archives share one MiddEval3/ tree.

    Unlike ``fetch_middlebury._safe_extract`` there is no single expected
    prefix per archive beyond ``MiddEval3``: the SDK, data and ground-truth
    zips all deliberately overlay the same directory.
    """
    root = root.resolve()
    for member in z.namelist():
        target = (root / member).resolve()
        if not target.is_relative_to(root):
            raise SystemExit(f"refusing to extract outside {root}: {member}")
        if not member.startswith("MiddEval3"):
            raise SystemExit(f"unexpected archive layout: {member!r} is not under MiddEval3/")
    z.extractall(root)


def fetch_file(filename: str, cfg: dict, root: Path, record: bool) -> str:
    url = f"{cfg['base_url']}/{filename}"
    zip_path = root / filename

    if not zip_path.exists():
        print(f"  fetching {url}")
        download(url, zip_path)
    else:
        print(f"  have {zip_path.name}")

    digest = sha256(zip_path)
    expected = (cfg.get("checksums") or {}).get(filename)
    if expected and expected != digest:
        raise SystemExit(
            f"checksum mismatch for {filename}\n"
            f"  expected {expected}\n"
            f"  got      {digest}\n"
            "Upstream data changed, or the file is truncated. Delete it and "
            "re-fetch. Do not update the checksum to match: every result citing "
            "this manifest is pinned to the bytes it recorded."
        )
    if not expected and not record:
        print(f"    (no recorded checksum; re-run with --record-checksums) {digest}")

    print(f"  extracting {filename}")
    with zipfile.ZipFile(zip_path) as z:
        _safe_extract_merged(z, root)
    return digest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", type=Path, default=CONFIG)
    ap.add_argument("--dry-run", action="store_true", help="print the plan and the disk cost")
    ap.add_argument(
        "--record-checksums",
        action="store_true",
        help="write the sha256 of each fetched zip back into the manifest",
    )
    ap.add_argument("--keep-zips", action="store_true", help="do not delete zips after extracting")
    args = ap.parse_args(argv)

    cfg = yaml.safe_load(args.config.read_text())["dataset"]
    root = data_root()
    print(f"data root: {root}")
    print(f"files:     {len(cfg['files'])}")

    if args.dry_run:
        print("\nwould fetch:")
        for f in cfg["files"]:
            state = "present" if (root / f).exists() else "missing"
            print(f"  {cfg['base_url']}/{f}   [{state}]")
        free = shutil.disk_usage(root if root.exists() else Path.home()).free
        print(f"\nfree on that volume: {free >> 30} GB")
        return 0

    root.mkdir(parents=True, exist_ok=True)
    digests: dict[str, str] = dict(cfg.get("checksums") or {})
    for i, filename in enumerate(cfg["files"], 1):
        print(f"\n[{i}/{len(cfg['files'])}] {filename}")
        digests[filename] = fetch_file(filename, cfg, root, args.record_checksums)
        # Written after every file, not once at the end -- see the lesson
        # recorded in fetch_middlebury.main.
        if args.record_checksums:
            _write_checksums(args.config, digests)
        if not args.keep_zips:
            (root / filename).unlink(missing_ok=True)

    print(f"\ndone. MiddEval3 tree under {root / 'MiddEval3'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
