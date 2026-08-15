"""Run identity: every result is addressable by a run-id bound to a git SHA.

The point is that six months from now a number in the paper can be traced to the
exact code and config that produced it. A result without a manifest is not a
result.
"""

from __future__ import annotations

import json
import platform
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np


def git_sha(short: bool = True) -> str:
    """Current commit SHA, or ``"nogit"`` outside a repository."""
    cmd = ["git", "rev-parse", "--short" if short else "HEAD", "HEAD"]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=5)
        return out.stdout.strip().split("\n")[0]
    except (subprocess.SubprocessError, FileNotFoundError):
        return "nogit"


def git_dirty() -> bool:
    """True when the working tree has uncommitted changes."""
    try:
        out = subprocess.run(
            ["git", "status", "--porcelain"], capture_output=True, text=True, check=True, timeout=5
        )
        return bool(out.stdout.strip())
    except (subprocess.SubprocessError, FileNotFoundError):
        return False


def make_run_id(tag: str = "run") -> str:
    """Timestamped, git-pinned identifier, e.g. ``exp001-20260815T142233-a1b2c3d``."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    return f"{tag}-{stamp}-{git_sha()}"


@dataclass
class RunContext:
    """Bundles run identity, seeded RNG, and the output directory.

    Writing the manifest is not optional: ``RunContext`` refuses to hand out an
    output directory without one.
    """

    tag: str = "run"
    seed: int = 0
    config: dict[str, Any] = field(default_factory=dict)
    root: Path = Path("results")

    def __post_init__(self) -> None:
        self.run_id = make_run_id(self.tag)
        self.rng = np.random.default_rng(self.seed)
        self.dir = self.root / self.run_id
        self.dir.mkdir(parents=True, exist_ok=True)
        self._write_manifest()

    def _write_manifest(self) -> None:
        manifest = {
            "run_id": self.run_id,
            "tag": self.tag,
            "seed": self.seed,
            "git_sha": git_sha(short=False),
            "git_dirty": git_dirty(),
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "python": platform.python_version(),
            "numpy": np.__version__,
            "config": self.config,
        }
        (self.dir / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str))

    def path(self, name: str) -> Path:
        """Path inside this run's output directory."""
        return self.dir / name
