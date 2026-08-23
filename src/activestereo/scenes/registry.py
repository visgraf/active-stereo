"""One dispatch point from a ``scene:`` config block to concrete scenes.

``configs/scene/*.yaml`` has carried a ``kind:`` field since the repository was
bootstrapped, and nothing ever read it. ``exp001``'s runner builds a
``RandomDotStereogram`` unconditionally, so ``configs/scene/textured_slant.yaml``
has been inert config for as long as it has existed -- a file that looks like it
configures something and does not. This is the reader.

Returns a **list**, always. A stimulus config describes a stimulus *set*: a
Middlebury corpus is ten scenes, a Blender chart sweep is twelve renders, and an
RDS is one. Making the single case return a one-element list costs a subscript
and stops every caller from branching on the arity of its own config.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from activestereo.scenes.base import Scene
from activestereo.scenes.depthmaps import corrugated, disk, slanted_plane, staircase
from activestereo.types import FloatArray

# Annotated rather than inferred: the four functions have different keyword
# signatures, so mypy joins them to bare `function` and then refuses to pass one
# to RandomDotStereogram, which asks for Callable[..., FloatArray].
DEPTH_FUNCTIONS: dict[str, Callable[..., FloatArray]] = {
    "disk": disk,
    "staircase": staircase,
    "slanted_plane": slanted_plane,
    "corrugated": corrugated,
}

#: Kinds a config may name but that have no implementation. Listed explicitly so
#: they fail with a reason rather than with a bare KeyError on ``kind``.
UNIMPLEMENTED = {
    "textured_slant": (
        "no textured-slant scene class exists. The config predates any "
        "implementation; it is a description of an intention, not a stimulus. "
        "Use kind: rds with depth_fn: slanted_plane for the geometry, or "
        "kind: blender_chart for a textured render."
    ),
}


def data_root() -> Path:
    """Where dataset blobs live: outside the repository, always (CLAUDE.md §2)."""
    return Path(os.environ.get("ACTIVESTEREO_DATA_ROOT", "~/datasets/middlebury2014")).expanduser()


def from_config(cfg: dict[str, Any]) -> list[Scene]:
    """Build every scene a config's ``scene:`` block describes.

    Parameters
    ----------
    cfg : a loaded config; only ``cfg["scene"]`` is read.

    Raises
    ------
    ValueError
        On an unknown or unimplemented ``kind``. Deliberately not a silent
        fallback to RDS: a runner that quietly substitutes a random-dot
        stereogram for the stimulus you asked for produces results that answer a
        different question than the one on the config.
    """
    if "scene" not in cfg:
        raise ValueError("config has no 'scene' block")
    sc = dict(cfg["scene"])
    kind = sc.pop("kind", None)
    if kind is None:
        raise ValueError(f"scene config has no 'kind'. Known kinds: {sorted(_BUILDERS)}")
    if kind in UNIMPLEMENTED:
        raise ValueError(f"scene kind {kind!r} is not implemented: {UNIMPLEMENTED[kind]}")
    if kind not in _BUILDERS:
        raise ValueError(f"unknown scene kind {kind!r}. Known kinds: {sorted(_BUILDERS)}")
    return _BUILDERS[kind](sc)


#: The ``scene:`` keys in ``configs/default.yaml``, which every scene config
#: inherits through ``defaults:`` whether or not its kind uses them. A rendered
#: corpus has no ``shape`` to choose and no ``placeholder_depth``, so these are
#: ignored rather than rejected. Anything left over that is *not* in here is
#: treated as a typo, because silently dropping ``dot_sizee`` would leave the
#: stimulus quietly at its default while the config claims otherwise.
#:
#: Kept in sync with ``configs/default.yaml`` by
#: ``tests/unit/test_scene_registry.py``, not by hope.
INHERITED_KEYS = {"shape", "depth_range", "placeholder_depth"}

#: Constructor arguments of RandomDotStereogram, as opposed to arguments of the
#: depth-map function it wraps. The split is by signature, not by convention.
RDS_KEYS = {"density", "dot_size", "binary", "noise"}


def _build_rds(sc: dict[str, Any]) -> list[Scene]:
    import inspect

    from activestereo.scenes.rds import RandomDotStereogram

    depth_fn = sc.pop("depth_fn", "disk")
    if depth_fn not in DEPTH_FUNCTIONS:
        raise ValueError(f"unknown depth_fn {depth_fn!r}. Known: {sorted(DEPTH_FUNCTIONS)}")
    fn = DEPTH_FUNCTIONS[depth_fn]

    shape = tuple(sc.pop("shape", (240, 320)))
    name = sc.pop("name", f"rds_{depth_fn}")

    # Route the rest by whose signature accepts it, so adding a parameter to a
    # depth function needs no change here.
    accepted = set(inspect.signature(fn).parameters) - {"shape"}
    depth_kwargs = {k: sc.pop(k) for k in list(sc) if k in accepted}
    rds_kwargs = {k: sc.pop(k) for k in list(sc) if k in RDS_KEYS}

    _reject_leftovers(sc, f"rds/{depth_fn}", sorted(accepted | RDS_KEYS))
    return [
        RandomDotStereogram(
            fn,
            name=name,
            shape=(int(shape[0]), int(shape[1])),
            **rds_kwargs,
            **depth_kwargs,
        )
    ]


def _reject_leftovers(sc: dict[str, Any], kind: str, accepted: list[str]) -> None:
    """Raise on unrecognised keys, and **drop** the inherited ones from ``sc``.

    Dropping is not incidental: builders that splat ``**sc`` into a constructor
    would otherwise forward ``shape`` and ``depth_range`` to classes that have no
    such parameters. Validating without consuming is what made this a bug rather
    than a no-op.
    """
    leftover = sorted(set(sc) - INHERITED_KEYS)
    if leftover:
        raise ValueError(
            f"scene kind {kind!r} does not use {leftover}. "
            f"Accepted here: {accepted}. "
            "Keys inherited from configs/default.yaml are ignored silently; "
            "anything else is treated as a typo rather than dropped, because a "
            "dropped key leaves the stimulus at its default while the config "
            "says otherwise."
        )
    for key in INHERITED_KEYS:
        sc.pop(key, None)


def _build_middlebury(sc: dict[str, Any]) -> list[Scene]:
    from activestereo.scenes.middlebury import MiddleburyScene

    root = Path(sc.pop("root", data_root())).expanduser()
    variant = sc.pop("variant", "perfect")
    downsample = int(sc.pop("downsample", 3))
    names = sc.pop("scenes", None)
    if not names:
        raise ValueError(
            "middlebury config lists no scenes. The scene list is a "
            "pre-registered experimental choice (ADR-0012), so it is required "
            "rather than defaulted to whatever happens to be on disk."
        )

    _reject_leftovers(sc, "middlebury", ["root", "variant", "downsample", "scenes", "tolerance"])
    missing = [n for n in names if not (root / f"{n}-{variant}").is_dir()]
    if missing:
        raise FileNotFoundError(
            f"not fetched under {root}: {missing}\nRun: python scripts/fetch_middlebury.py"
        )
    return [MiddleburyScene(root / f"{n}-{variant}", downsample=downsample, **sc) for n in names]


def _build_blender_chart(sc: dict[str, Any]) -> list[Scene]:
    from activestereo.scenes.blender import BlenderRenderScene

    root = Path(sc.pop("stimulus_root", "results/stimuli/chart"))
    lighting = sc.pop("lighting", ["ambient", "key", "grazing"])
    permutations = sc.pop("permutations", [0, 1, 2, 3])
    _reject_leftovers(sc, "blender_chart", ["stimulus_root", "lighting", "permutations"])
    dirs = [root / f"{light}_p{p}" for light in lighting for p in permutations]
    missing = [str(d) for d in dirs if not d.is_dir()]
    if missing:
        raise FileNotFoundError(
            f"missing renders: {missing[:3]}{'...' if len(missing) > 3 else ''}\n"
            "Run: python scripts/render_chart_sweep.py --out results/stimuli/chart"
        )
    return [BlenderRenderScene(d) for d in dirs]


_BUILDERS = {
    "rds": _build_rds,
    "middlebury": _build_middlebury,
    "blender_chart": _build_blender_chart,
}
