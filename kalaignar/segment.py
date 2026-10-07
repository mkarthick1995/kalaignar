"""Stages 2–3 — Segment & clean: crop each part box from the canonical canvas,
extract the ink drawing, fill enclosed interiors, output RGBA parts.

Parts render as dark ink + near-white interior so the game's per-player
body_color modulate can tint them (same convention as the placeholders).
An optional palette (palette.py) recolors ink/fill afterwards using `ink`."""

from dataclasses import dataclass

import cv2
import numpy as np

from . import layout

INK_COLOR = 45
FILL_COLOR = 235
BOX_INSET = 10  # skip the printed guide outline
MIN_INK_PIXELS = 220  # below this a box counts as "not drawn"


@dataclass
class Part:
    name: str
    rgba: np.ndarray  # (h, w, 4) uint8, tight-cropped
    pivot: tuple[float, float]  # pivot position inside the cropped image
    ink: np.ndarray  # (h, w) bool — True where the artist's line is
    origin: tuple[int, int]  # crop's top-left in canonical canvas coordinates


def _extract_one(canvas: np.ndarray, name: str) -> Part | None:
    bx, by, bw, bh = layout.PARTS[name]["box"]
    px, py = layout.PARTS[name]["pivot"]
    crop = canvas[
        by + BOX_INSET : by + bh - BOX_INSET, bx + BOX_INSET : bx + bw - BOX_INSET
    ]
    ink = (crop < layout.INK_THRESHOLD).astype(np.uint8) * 255
    ink = cv2.morphologyEx(ink, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    ink = cv2.medianBlur(ink, 3)
    if int(np.count_nonzero(ink)) < MIN_INK_PIXELS:
        return None

    # Fill enclosed interiors: flood the outside, everything else is "inside".
    h, w = ink.shape
    flood = ink.copy()
    ff_mask = np.zeros((h + 2, w + 2), np.uint8)
    cv2.floodFill(flood, ff_mask, (0, 0), 255)
    inside = cv2.bitwise_or(ink, cv2.bitwise_not(flood))

    alpha = cv2.GaussianBlur(inside, (3, 3), 0)
    value = np.where(ink > 0, INK_COLOR, FILL_COLOR).astype(np.uint8)
    rgba = np.dstack([value, value, value, alpha])

    # Tight crop, keeping the pivot location consistent.
    ys, xs = np.nonzero(alpha)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    rgba = rgba[y0:y1, x0:x1]
    origin = (bx + BOX_INSET + int(x0), by + BOX_INSET + int(y0))
    pivot_local = (px - origin[0], py - origin[1])
    return Part(
        name=name, rgba=rgba, pivot=pivot_local,
        ink=ink[y0:y1, x0:x1] > 0, origin=origin,
    )


def extract_parts(canvas: np.ndarray) -> dict[str, Part]:
    """Canonical canvas -> {part name: Part}. Missing weapon is fine (unarmed);
    other missing parts raise."""
    parts: dict[str, Part] = {}
    missing: list[str] = []
    for name in layout.PARTS:
        part = _extract_one(canvas, name)
        if part is not None:
            parts[name] = part
        elif name != "weapon":
            missing.append(name)
    if missing:
        raise ValueError(f"no drawing found in: {', '.join(missing)}")
    return parts
