"""Palette: flat-fill colors chosen by the artist, applied after segmentation.

palette.json:
    {
      "ink":  "#2d2d2d",                  # line color, every part
      "fill": "#ebebeb",                  # interior color, every part
      "parts": {                          # optional per-part overrides
        "torso":  {"fill": "#d9a066"},
        "weapon": {"fill": "#f5ebd2", "ink": "#4a3520"}
      }
    }

Every key is optional; the defaults reproduce the unpaletted look (dark ink,
near-white fill). The game multiplies sprites by the player's body_color, so
light fills keep that tint readable — saturated fills will darken under it.
"""

import json
from pathlib import Path

import numpy as np

from . import layout
from .segment import FILL_COLOR, INK_COLOR, Part

DEFAULT = {
    "ink": "#%02x%02x%02x" % ((INK_COLOR,) * 3),
    "fill": "#%02x%02x%02x" % ((FILL_COLOR,) * 3),
}


class PaletteError(ValueError):
    pass


def parse_color(value: str) -> tuple[int, int, int]:
    """'#rrggbb' or '#rgb' -> (r, g, b)."""
    if not isinstance(value, str) or not value.startswith("#"):
        raise PaletteError(f"color must be a '#rrggbb' string, got {value!r}")
    hexpart = value[1:]
    if len(hexpart) == 3:
        hexpart = "".join(c * 2 for c in hexpart)
    if len(hexpart) != 6:
        raise PaletteError(f"color must be '#rgb' or '#rrggbb', got {value!r}")
    try:
        return tuple(int(hexpart[i : i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        raise PaletteError(f"not a hex color: {value!r}") from None


def load(path: Path) -> dict:
    """Read + validate palette.json. Returns {part: {"ink": rgb, "fill": rgb}}."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise PaletteError(f"{path}: invalid JSON ({e})") from None
    return resolve(raw)


def resolve(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise PaletteError("palette must be a JSON object")
    unknown = set(raw) - {"ink", "fill", "parts"}
    if unknown:
        raise PaletteError(f"unknown palette keys: {', '.join(sorted(unknown))}")
    overrides = raw.get("parts", {})
    bad = set(overrides) - set(layout.PARTS)
    if bad:
        raise PaletteError(
            f"unknown parts in palette: {', '.join(sorted(bad))} "
            f"(have: {', '.join(layout.PARTS)})"
        )
    base_ink = raw.get("ink", DEFAULT["ink"])
    base_fill = raw.get("fill", DEFAULT["fill"])
    resolved = {}
    for name in layout.PARTS:
        part = overrides.get(name, {})
        extra = set(part) - {"ink", "fill"}
        if extra:
            raise PaletteError(f"parts.{name}: unknown keys {', '.join(sorted(extra))}")
        resolved[name] = {
            "ink": parse_color(part.get("ink", base_ink)),
            "fill": parse_color(part.get("fill", base_fill)),
        }
    return resolved


def apply(parts: dict[str, Part], palette: dict) -> None:
    """Recolor each part in place: ink pixels -> ink color, the rest -> fill.
    Alpha is untouched."""
    for name, part in parts.items():
        colors = palette[name]
        rgb = np.where(part.ink[:, :, None], colors["ink"], colors["fill"])
        part.rgba[:, :, :3] = rgb.astype(np.uint8)


def save_starter(path: Path) -> None:
    """Write a palette.json with every part listed, ready to edit."""
    starter = {
        "ink": DEFAULT["ink"],
        "fill": DEFAULT["fill"],
        "parts": {name: {"fill": DEFAULT["fill"]} for name in layout.PARTS},
    }
    Path(path).write_text(json.dumps(starter, indent=2) + "\n", encoding="utf-8")
