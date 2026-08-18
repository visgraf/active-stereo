"""Fetch the Middlebury 2014 stereo datasets into an external data root.

Blobs never enter the repository. They land in ``$ACTIVESTEREO_DATA_ROOT``
(default ``~/datasets/middlebury2014``), leaving ``data/`` for DVC pointers as
CLAUDE.md §2 requires.

    python scripts/fetch_middlebury.py --dry-run
    python scripts/fetch_middlebury.py --record-checksums     # first fetch
    python scripts/fetch_middlebury.py                        # verifies

The scene list and the citation live in ``configs/dataset/middlebury2014.yaml``
and are deliberately not arguments: which scenes we evaluate on is a
pre-registered experimental choice, not a command-line convenience.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sys
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

import yaml

CONFIG = Path(__file__).resolve().parent.parent / "configs" / "dataset" / "middlebury2014.yaml"
CHUNK = 1 << 20


def data_root() -> Path:
    """Where blobs live. Outside the repository, always."""
    return Path(os.environ.get("ACTIVESTEREO_DATA_ROOT", "~/datasets/middlebury2014")).expanduser()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(CHUNK):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, dest: Path, attempts: int = 4) -> None:
    """Download to a ``.part`` file and rename on success, retrying on failure.

    An interrupted download that keeps the final name is indistinguishable from a
    complete one until something downstream reads a truncated zip and reports a
    corrupt PFM, which is a long way from the actual cause.

    Retries because ten 95 MB transfers over one connection will meet a timeout
    eventually, and the first version of this script turned one transient failure
    into an aborted corpus. A socket timeout is not a reason to re-download the
    six scenes that already succeeded.
    """
    part = dest.with_suffix(dest.suffix + ".part")
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(url, timeout=120) as response:
                total = int(response.headers.get("content-length", 0))
                done = 0
                with part.open("wb") as f:
                    while chunk := response.read(CHUNK):
                        f.write(chunk)
                        done += len(chunk)
                        if total:
                            pct = 100.0 * done / total
                            print(
                                f"\r    {done >> 20:5d} / {total >> 20:5d} MB  {pct:5.1f}%", end=""
                            )
                print()
            part.rename(dest)
            return
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            part.unlink(missing_ok=True)
            if attempt == attempts:
                raise SystemExit(
                    f"download failed after {attempts} attempts: {url}\n  {exc}\n"
                    "Already-fetched scenes are kept; re-run to resume."
                ) from exc
            wait = 5 * 2 ** (attempt - 1)
            print(f"    attempt {attempt}/{attempts} failed ({exc}); retrying in {wait}s")
            time.sleep(wait)


def fetch_scene(scene: str, cfg: dict[str, Any], root: Path, record: bool) -> str:
    variant = cfg["variant"]
    name = f"{scene}-{variant}"
    url = f"{cfg['base_url']}/{name}.zip"
    zip_path = root / f"{name}.zip"
    scene_dir = root / name

    if not zip_path.exists():
        print(f"  fetching {url}")
        download(url, zip_path)
    else:
        print(f"  have {zip_path.name}")

    digest = sha256(zip_path)
    expected = cfg.get("checksums", {}).get(scene)
    if expected and expected != digest:
        raise SystemExit(
            f"checksum mismatch for {name}.zip\n"
            f"  expected {expected}\n"
            f"  got      {digest}\n"
            "Upstream data changed, or the file is truncated. Delete it and "
            "re-fetch. Do not update the checksum to match: every result citing "
            "this manifest is pinned to the bytes it recorded."
        )
    if not expected and not record:
        print(f"    (no recorded checksum; re-run with --record-checksums) {digest}")

    if not scene_dir.exists():
        print(f"  extracting {name}/")
        with zipfile.ZipFile(zip_path) as z:
            _safe_extract(z, root, name)

    return digest


def _safe_extract(z: zipfile.ZipFile, root: Path, expected_prefix: str) -> None:
    """Extract, refusing any member that would escape ``root``.

    A zip can name ``../../etc/thing``. This corpus is trustworthy, but a fetch
    script that writes wherever an archive tells it to is a bad habit to leave in
    a repo that will grow more of them.
    """
    root = root.resolve()
    for member in z.namelist():
        target = (root / member).resolve()
        if not target.is_relative_to(root):
            raise SystemExit(f"refusing to extract outside {root}: {member}")
        if not member.startswith(expected_prefix):
            raise SystemExit(
                f"unexpected archive layout: {member!r} is not under {expected_prefix}"
            )
    z.extractall(root)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", type=Path, default=CONFIG)
    ap.add_argument("--scenes", nargs="*", help="subset of the manifest; default is all of it")
    ap.add_argument("--dry-run", action="store_true", help="print the plan and the disk cost")
    ap.add_argument(
        "--record-checksums",
        action="store_true",
        help="write the sha256 of each fetched zip back into the manifest",
    )
    ap.add_argument("--keep-zips", action="store_true", help="do not delete zips after extracting")
    args = ap.parse_args(argv)

    raw = yaml.safe_load(args.config.read_text())
    cfg = raw["dataset"]
    scenes = args.scenes or cfg["scenes"]
    unknown = sorted(set(scenes) - set(cfg["scenes"]))
    if unknown:
        raise SystemExit(
            f"not in the pre-registered scene list: {unknown}\n"
            f"Manifest has: {cfg['scenes']}\n"
            "Adding a scene after seeing results is post-hoc selection. If the "
            "list is genuinely wrong, change the manifest and say so in the "
            "lab notebook."
        )

    root = data_root()
    print(f"data root: {root}")
    print(f"variant:   {cfg['variant']}  resolution: {cfg['resolution']}")
    print(f"scenes:    {len(scenes)}  ({', '.join(scenes)})")

    if args.dry_run:
        print("\nwould fetch (~95 MB each, ~1 GB total):")
        for scene in scenes:
            name = f"{scene}-{cfg['variant']}"
            state = "present" if (root / name).exists() else "missing"
            print(f"  {cfg['base_url']}/{name}.zip   [{state}]")
        free = shutil.disk_usage(root if root.exists() else Path.home()).free
        print(f"\nfree on that volume: {free >> 30} GB")
        return 0

    root.mkdir(parents=True, exist_ok=True)
    digests: dict[str, str] = dict(cfg.get("checksums") or {})
    for i, scene in enumerate(scenes, 1):
        print(f"\n[{i}/{len(scenes)}] {scene}")
        digests[scene] = fetch_scene(scene, cfg, root, args.record_checksums)

        # Written after every scene, not once at the end. The first version wrote
        # only on completion, a download failed on scene 7 of 10, and the six
        # digests already computed were lost -- while the zips they described had
        # been deleted, so they could not be recomputed without re-downloading
        # 570 MB. A checksum that exists only in memory is not a record.
        if args.record_checksums:
            _write_checksums(args.config, digests)
        if not args.keep_zips:
            (root / f"{scene}-{cfg['variant']}.zip").unlink(missing_ok=True)

    if args.record_checksums:
        print(f"\nrecorded {len(digests)} checksums in {args.config}")

    print(f"\ndone. {len(scenes)} scenes under {root}")
    return 0


def _write_checksums(config_path: Path, digests: dict[str, str]) -> None:
    """Rewrite only the ``checksums:`` block, by hand.

    Round-tripping the file through ``yaml.safe_dump`` would discard every comment
    in it, and the comments are where the pre-registration argument for the scene
    list lives -- the most load-bearing thing in the manifest.
    """
    text = config_path.read_text()
    head, sep, _ = text.partition("\n  checksums:")
    if not sep:
        raise SystemExit(f"{config_path} has no `  checksums:` block to update")
    body = yaml.safe_dump({"checksums": {k: digests[k] for k in sorted(digests)}}, sort_keys=True)
    config_path.write_text(
        head + "\n" + "\n".join(f"  {line}" for line in body.rstrip().split("\n")) + "\n"
    )


if __name__ == "__main__":
    sys.exit(main())
