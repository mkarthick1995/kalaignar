"""Synthetic end-to-end test: programmatically 'draw' a character onto the
template, photograph it (with a simulated perspective tilt), and run the whole
pipeline. Verifies frame detection, ink extraction with hole-filling, the
puppet renderer, and export naming — all before any real drawing exists.

Run from the repo root:  python tests/run_test.py
"""

import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kalaignar import export, ingest, segment, template  # noqa: E402
from kalaignar import layout  # noqa: E402

FAILURES = 0


def check(cond: bool, label: str) -> None:
    global FAILURES
    print(("  PASS  " if cond else "  FAIL  ") + label)
    if not cond:
        FAILURES += 1


def draw_fake_character(img: Image.Image) -> None:
    """Outline-only shapes in each part box (interiors must get auto-filled)."""
    d = ImageDraw.Draw(img)

    def box(name):
        bx, by, bw, bh = layout.PARTS[name]["box"]
        return bx, by, bw, bh

    bx, by, bw, bh = box("head")  # round head with a topknot
    d.ellipse([bx + 60, by + 60, bx + bw - 60, by + bh - 40], outline=0, width=9)
    bx, by, bw, bh = box("torso")  # tapered torso
    d.polygon(
        [(bx + 90, by + 30), (bx + bw - 90, by + 30), (bx + bw - 60, by + bh - 20),
         (bx + 60, by + bh - 20)],
        outline=0, width=9,
    )
    for name in ("arm_front", "arm_rear", "leg_front", "leg_rear"):
        bx, by, bw, bh = box(name)
        d.rounded_rectangle(
            [bx + bw // 2 - 40, by + 15, bx + bw // 2 + 40, by + bh - 30],
            radius=35, outline=0, width=9,
        )
    bx, by, bw, bh = box("weapon")  # long thin staff
    d.rounded_rectangle(
        [bx + bw // 2 - 18, by + 20, bx + bw // 2 + 18, by + bh - 20],
        radius=16, outline=0, width=8,
    )


def simulate_photo(sheet: np.ndarray) -> np.ndarray:
    """Slight perspective tilt + border, as if photographed on a desk."""
    h, w = sheet.shape
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    dst = np.float32([[60, 40], [w + 25, 70], [w - 30, h + 60], [15, h + 10]])
    m = cv2.getPerspectiveTransform(src, dst)
    return cv2.warpPerspective(sheet, m, (w + 90, h + 110), borderValue=170)


def main() -> int:
    tpl = template.make_template()
    draw_fake_character(tpl)
    photo = simulate_photo(np.array(tpl))
    photo_bgr = cv2.cvtColor(photo, cv2.COLOR_GRAY2BGR)

    canvas = ingest.warp_to_canvas(photo_bgr)
    check(canvas.shape == (layout.CANVAS_H, layout.CANVAS_W), "ingest: warped to canonical canvas")

    parts = segment.extract_parts(canvas)
    check(len(parts) == 7, f"segment: all 7 parts found (got {len(parts)})")
    head = parts["head"]
    interior = head.rgba[head.rgba.shape[0] // 2, head.rgba.shape[1] // 2]
    check(interior[3] > 200, "segment: enclosed interior auto-filled (head center opaque)")
    check(
        interior[0] > 180, "segment: interior is light (tintable), not ink-dark"
    )

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        written = export.export_character(parts, "bengal_lathi", out, artist="synthetic")
        names = {p.name for p in written}
        for expected in ("idle@4x8.png", "walk@6x10.png", "jab@4x20.png", "portrait.png"):
            check(expected in names, f"export: {expected} written")
        strip = Image.open(out / "walk@6x10.png")
        check(strip.size == (128 * 6, 192), "export: walk strip is 6 frames of 128x192")
        frame = strip.crop((0, 0, 128, 192))
        alpha = np.array(frame)[:, :, 3]
        coverage = float((alpha > 60).mean())
        check(0.03 < coverage < 0.6, f"render: frame has sane body coverage ({coverage:.2%})")
        feet_zone = alpha[170:192, :]
        check(feet_zone.max() > 60, "render: content reaches the feet baseline")

    print("=== kalaignar synthetic test: %s ===" % ("FAILED" if FAILURES else "OK"))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
