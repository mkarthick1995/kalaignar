"""Rig: per-part pivot overrides, stored in canonical canvas coordinates.

rig.json:
    {"pivots": {"arm_front": [1092, 158], "head": [250, 470]}}

Canvas coordinates (the template's own space, same as layout.PARTS) rather
than part-local ones, so a rig survives redrawing a part: the tight crop
moves, the joint on the sheet doesn't. Parts not listed keep the template's
printed pivot cross.
"""

import json
from pathlib import Path

from . import layout
from .segment import Part


class RigError(ValueError):
    pass


def load(path: Path) -> dict[str, tuple[float, float]]:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise RigError(f"{path}: invalid JSON ({e})") from None
    pivots = raw.get("pivots") if isinstance(raw, dict) else None
    if not isinstance(pivots, dict):
        raise RigError(f"{path}: expected {{\"pivots\": {{part: [x, y]}}}}")
    out = {}
    for name, xy in pivots.items():
        if name not in layout.PARTS:
            raise RigError(f"unknown part in rig: {name} (have: {', '.join(layout.PARTS)})")
        if not (isinstance(xy, list) and len(xy) == 2
                and all(isinstance(v, (int, float)) for v in xy)):
            raise RigError(f"pivots.{name}: expected [x, y], got {xy!r}")
        out[name] = (float(xy[0]), float(xy[1]))
    return out


def save(path: Path, pivots: dict[str, tuple[float, float]]) -> None:
    # One part per line — readable and diff-friendly.
    rows = [
        f'    "{n}": [{round(float(x), 1):g}, {round(float(y), 1):g}]'
        for n, (x, y) in pivots.items()
    ]
    Path(path).write_text(
        '{\n  "pivots": {\n' + ",\n".join(rows) + "\n  }\n}\n", encoding="utf-8"
    )


def canvas_pivots(parts: dict[str, Part]) -> dict[str, tuple[float, float]]:
    """The pivots currently in effect, in canvas coordinates."""
    return {
        n: (p.origin[0] + p.pivot[0], p.origin[1] + p.pivot[1]) for n, p in parts.items()
    }


def apply(parts: dict[str, Part], pivots: dict[str, tuple[float, float]]) -> None:
    """Move each listed part's pivot (in place). Rig entries for parts that
    weren't drawn (e.g. no weapon) are ignored."""
    for name, (x, y) in pivots.items():
        part = parts.get(name)
        if part is not None:
            part.pivot = (x - part.origin[0], y - part.origin[1])
