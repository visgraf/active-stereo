"""YAML config loading with shallow composition via a ``defaults`` key."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_config(path: str | Path) -> dict[str, Any]:
    """Load a YAML config, resolving a ``defaults:`` list of relative includes.

    Later entries override earlier ones; the file's own keys override all
    includes. Deliberately simple -- if this grows a third feature, replace it
    with Hydra rather than reinventing it.
    """
    path = Path(path)
    with path.open() as f:
        raw = yaml.safe_load(f) or {}

    merged: dict[str, Any] = {}
    for include in raw.pop("defaults", []) or []:
        merged = _deep_merge(merged, load_config(path.parent / include))
    return _deep_merge(merged, raw)


def _deep_merge(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    out = dict(a)
    for k, v in b.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out
