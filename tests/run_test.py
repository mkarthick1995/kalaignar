"""Synthetic end-to-end test: programmatically 'draw' a character onto the
template, photograph it (with a simulated perspective tilt), and run the whole
pipeline. Verifies frame detection, ink extraction with hole-filling, the
puppet renderer, and export naming — all before any real drawing exists.

Run from the repo root:  python tests/run_test.py
"""

import copy
import math
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kalaignar import export, ingest, segment, template  # noqa: E402
from kalaignar import layout, palette, rig  # noqa: E402

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

    # Palette: per-part fill override, global ink; alpha untouched.
    colors = palette.resolve({"ink": "#102030", "parts": {"torso": {"fill": "#c86432"}}})
    tinted = copy.deepcopy(parts)
    palette.apply(tinted, colors)
    t = tinted["torso"]
    t_mid = t.rgba[t.rgba.shape[0] // 2, t.rgba.shape[1] // 2]
    check(tuple(t_mid[:3]) == (0xC8, 0x64, 0x32), "palette: torso fill override applied")
    h = tinted["head"].rgba
    h_mid = h[h.shape[0] // 2, h.shape[1] // 2]
    check(tuple(h_mid[:3]) == (235, 235, 235), "palette: other parts keep default fill")
    ink_px = t.rgba[t.ink]
    check(len(ink_px) > 0 and (ink_px[:, :3] == (0x10, 0x20, 0x30)).all(),
          "palette: global ink color applied to line pixels")
    check(np.array_equal(t.rgba[:, :, 3], parts["torso"].rgba[:, :, 3]),
          "palette: alpha unchanged")
    try:
        palette.resolve({"parts": {"tail": {"fill": "#fff"}}})
        check(False, "palette: unknown part rejected")
    except palette.PaletteError:
        check(True, "palette: unknown part rejected")

    # Rig: canvas-space pivots round-trip through rig.json and move the joint.
    pivots = rig.canvas_pivots(parts)
    tx, ty = layout.PARTS["arm_front"]["pivot"]
    ax, ay = pivots["arm_front"]
    check(abs(ax - tx) < 1e-6 and abs(ay - ty) < 1e-6,
          "rig: default pivot = template cross (canvas coords)")
    moved = copy.deepcopy(parts)
    with tempfile.TemporaryDirectory() as tmp:
        rig_path = Path(tmp) / "rig.json"
        rig.save(rig_path, {"arm_front": (tx + 6, ty + 20)})
        rig.apply(moved, rig.load(rig_path))
    mx, my = rig.canvas_pivots(moved)["arm_front"]
    check((round(mx), round(my)) == (tx + 6, ty + 20), "rig: override saved, loaded, applied")
    check(moved["head"].pivot == parts["head"].pivot, "rig: unlisted parts untouched")

    # Editor state (headless — compose() only, no window).
    from kalaignar.editor import PivotEditor

    ed = PivotEditor(copy.deepcopy(parts), "bengal_lathi")
    before = ed.compose()
    ed.nudge(0, -25)
    after = ed.compose()
    check(ed.dirty and ed.pivots()["head"][1] == layout.PARTS["head"]["pivot"][1] - 25,
          "editor: nudge moves the selected part's pivot")
    check(not np.array_equal(before, after), "editor: preview re-renders after a change")
    ed.click(-5000, -5000)
    hx, hy = ed.pivots()["head"]
    bx, by, _, _ = layout.PARTS["head"]["box"]
    check((hx, hy) == (bx, by), "editor: clicks clamp to the part's template box")
    ed.reset()
    check(ed.pivots()["head"] == tuple(map(float, layout.PARTS["head"]["pivot"])),
          "editor: reset returns to the template cross")

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

    # Rotation regression: a part must stay visible at every angle, with its
    # pivot on the joint and its far end on the target (limbs held near
    # horizontal used to render fully transparent).
    from kalaignar.render import SS, PuppetRenderer

    bar = np.zeros((400, 60, 4), np.uint8)
    bar[:, :, 3] = 255
    bar[:, :, :3] = 200
    bar[0:6, 27:33, :3] = (255, 0, 0)  # pivot marker
    bar[394:400, 27:33, :3] = (0, 0, 255)  # tip marker
    probe = PuppetRenderer({"arm_front": segment.Part(
        "arm_front", bar, (30, 3), np.zeros((400, 60), bool), (0, 0))})

    def marker(arr, pos, ch):
        m = (arr[:, :, ch] > 150) & (arr[:, :, (ch + 2) % 3] < 90) & (arr[:, :, 3] > 200)
        ys, xs = np.nonzero(m)
        if len(xs) == 0:
            return (1e9, 1e9)
        return ((xs.mean() + pos[0]) / SS, (ys.mean() + pos[1]) / SS)

    worst = 0.0
    for deg in range(0, 360, 15):
        a = math.radians(deg)
        joint, tgt = (64, 96), (64 + 40 * math.sin(a), 96 + 40 * math.cos(a))
        img, pos = probe._span("arm_front", joint, tgt)
        arr = np.array(img).astype(int)
        worst = max(worst, math.dist(marker(arr, pos, 0), joint),
                    math.dist(marker(arr, pos, 2), tgt))
    check(worst < 1.5, f"render: parts placed correctly at all 24 angles (max err {worst:.2f}px)")

    # Whip: with whip_curve the blade tip lands on the generator's polyline end,
    # not where a rigid blade would point.
    from kalaignar.render import ARM_LEN, CX, TORSO_LEN

    def whip_tip(pose, curve):
        hip = (CX, pose["hip_y"])
        sh = (hip[0], hip[1] - TORSO_LEN + 5.0)
        x, y = sh[0] + ARM_LEN, sh[1]  # front_arm = 0 -> hand straight forward
        seg, ang = pose["staff_len"] / 8, pose["staff_angle"]
        for _ in range(8):
            x, y = x + math.cos(ang) * seg, y - math.sin(ang) * seg
            ang -= curve
        return x, y

    whip_pose = {"hip_y": 140, "front_arm": 0.0, "staff_angle": 2.0, "staff_len": 60.0,
                 "whip_curve": 0.3}
    weapon_only = PuppetRenderer({"weapon": parts["weapon"]})
    alpha = np.array(weapon_only.render_frame(whip_pose))[:, :, 3]

    def ink_near(pt, r=3):
        x, y = int(round(pt[0])), int(round(pt[1]))
        return int(alpha[max(y - r, 0) : y + r + 1, max(x - r, 0) : x + r + 1].max())

    curved, straight = whip_tip(whip_pose, 0.3), whip_tip(whip_pose, 0.0)
    check(ink_near(curved) > 60 and ink_near(straight) < 20,
          "whip: urumi blade bends along the game's polyline")

    # Smear: fast strikes gain a ghost trail behind the real frame; first
    # frames, still frames and timing are untouched.
    from kalaignar import smear
    from kalaignar.poses import CHARACTER_POSES

    jab = CHARACTER_POSES["bengal_lathi"]["jab"][2]
    renderer_full = PuppetRenderer(parts)
    plain_strip = np.array(renderer_full.render_animation(jab))
    smear_strip = np.array(smear.render_animation(renderer_full, jab))
    check(plain_strip.shape == smear_strip.shape, "smear: strip size (frame count) unchanged")
    check(np.array_equal(plain_strip[:, :128], smear_strip[:, :128]),
          "smear: first frame has no trail")
    f1 = slice(128, 256)
    extra = (smear_strip[:, f1, 3] > 20) & (plain_strip[:, f1, 3] <= 20)
    check(int(extra.sum()) > 40, f"smear: fast jab frame gains a trail ({int(extra.sum())} px)")
    still = jab[0]
    check(np.array_equal(np.array(smear.render_frame(renderer_full, still, still)),
                         np.array(renderer_full.render_frame(still))),
          "smear: no trail when nothing moves")
    mid = smear.lerp_pose({"front_arm": 3.0}, {"front_arm": -3.0}, 0.5)["front_arm"]
    check(abs(abs(mid) - math.pi) < 1e-6, "smear: angles interpolate along the shortest arc")

    # Every fighter's full pose set must render (one frame per animation).
    check(len(CHARACTER_POSES) == 8, f"poses: 8 characters synced ({len(CHARACTER_POSES)})")
    renderer = PuppetRenderer(parts)
    total_anims = 0
    bad = []
    for character, anims in CHARACTER_POSES.items():
        if len(anims) != 13:
            bad.append(f"{character} has {len(anims)} anims")
        for anim, (fps, _loop, poses) in anims.items():
            total_anims += 1
            frame = renderer.render_frame(poses[0])
            if int(np.array(frame)[:, :, 3].max()) <= 60:
                bad.append(f"{character}/{anim} rendered empty")
    check(not bad, "poses: every animation of every fighter renders (%d checked)%s"
          % (total_anims, "" if not bad else " — " + "; ".join(bad[:4])))

    # CLI end to end: photo file + palette + rig + smear -> strips and rig.json.
    from kalaignar import cli

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        cv2.imwrite(str(tmp / "photo.png"), photo)
        (tmp / "palette.json").write_text('{"fill": "#f0e0d0"}', encoding="utf-8")
        (tmp / "rig.json").write_text('{"pivots": {"head": [250, 470]}}', encoding="utf-8")
        code = cli.main(["process", str(tmp / "photo.png"), "--character", "kerala_kalari",
                         "--out", str(tmp / "out"), "--palette", str(tmp / "palette.json"),
                         "--rig", str(tmp / "rig.json"), "--smear"])
        saved = rig.load(tmp / "out" / "rig.json") if code == 0 else {}
        check(code == 0 and (tmp / "out" / "lash@5x14.png").exists()
              and saved.get("head") == (250.0, 470.0),
              "cli: process with --palette --rig --smear writes strips + rig.json")

    print("=== kalaignar synthetic test: %s ===" % ("FAILED" if FAILURES else "OK"))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
