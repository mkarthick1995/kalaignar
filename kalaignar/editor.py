"""Pivot editor: click each part's joint, watch the puppet update live.

    python -m kalaignar pivots photo.jpg --character bengal_lathi --rig rig.json

Left: the selected part inside its template box, with the pivot cross.
Right: a live render of the chosen animation frame.

  click            set pivot          n / p     next / previous part
  w a s d          nudge pivot 1px    r         reset part to template cross
  ] / [            next / prev anim   . / ,     next / prev frame
  S (shift+s)      save rig.json      q / Esc   quit

The state logic lives in PivotEditor (testable headless); run() is the thin
OpenCV window loop around it.
"""

from pathlib import Path

import cv2
import numpy as np

from . import layout, rig
from .poses import CHARACTER_POSES
from .render import FRAME_H, FRAME_W, PuppetRenderer
from .segment import Part

VIEW_W, VIEW_H = 520, 640  # part panel
PREVIEW_SCALE = 3
HEADER_H = 54
WINDOW = "kalaignar pivots"


def _checker(h: int, w: int, size: int = 16) -> np.ndarray:
    yy, xx = np.mgrid[0:h, 0:w]
    tile = (((yy // size) + (xx // size)) % 2).astype(np.uint8)
    gray = np.where(tile, 228, 245).astype(np.uint8)
    return np.dstack([gray, gray, gray])


def _over(bg: np.ndarray, rgba: np.ndarray, x: int, y: int) -> None:
    """Alpha-composite an RGB(A) image onto a BGR background in place (clipped)."""
    h, w = rgba.shape[:2]
    x0, y0 = max(x, 0), max(y, 0)
    x1, y1 = min(x + w, bg.shape[1]), min(y + h, bg.shape[0])
    if x1 <= x0 or y1 <= y0:
        return
    src = rgba[y0 - y : y1 - y, x0 - x : x1 - x]
    a = src[:, :, 3:4].astype(np.float32) / 255.0
    bgr = src[:, :, 2::-1].astype(np.float32)
    region = bg[y0:y1, x0:x1].astype(np.float32)
    bg[y0:y1, x0:x1] = (bgr * a + region * (1 - a)).astype(np.uint8)


class PivotEditor:
    def __init__(self, parts: dict[str, Part], character: str):
        if character not in CHARACTER_POSES:
            raise ValueError(f"unknown character '{character}'")
        self.parts = parts
        self.names = [n for n in layout.PARTS if n in parts]
        self.index = 0
        self.anims = list(CHARACTER_POSES[character].items())
        self.anim_index = 0
        self.frame_index = 0
        self.dirty = False
        self._renderer = PuppetRenderer(parts)

    # -- state -----------------------------------------------------------

    @property
    def current(self) -> str:
        return self.names[self.index]

    def pivots(self) -> dict[str, tuple[float, float]]:
        return rig.canvas_pivots(self.parts)

    def _view_transform(self) -> tuple[float, int, int]:
        """Scale + offset mapping the current part's template box into the panel."""
        bx, by, bw, bh = layout.PARTS[self.current]["box"]
        scale = min((VIEW_W - 20) / bw, (VIEW_H - 20) / bh)
        ox = int((VIEW_W - bw * scale) / 2)
        oy = int((VIEW_H - bh * scale) / 2)
        return scale, ox, oy

    def set_pivot_canvas(self, x: float, y: float) -> None:
        """Set the current part's pivot, clamped to its template box."""
        bx, by, bw, bh = layout.PARTS[self.current]["box"]
        x = min(max(x, bx), bx + bw)
        y = min(max(y, by), by + bh)
        rig.apply(self.parts, {self.current: (x, y)})
        self._changed()

    def click(self, vx: int, vy: int) -> None:
        """A click at panel pixel (vx, vy) — panel coordinates, header excluded."""
        scale, ox, oy = self._view_transform()
        bx, by, _, _ = layout.PARTS[self.current]["box"]
        self.set_pivot_canvas(bx + (vx - ox) / scale, by + (vy - oy) / scale)

    def nudge(self, dx: float, dy: float) -> None:
        x, y = self.pivots()[self.current]
        self.set_pivot_canvas(x + dx, y + dy)

    def reset(self) -> None:
        self.set_pivot_canvas(*layout.PARTS[self.current]["pivot"])

    def step_part(self, d: int) -> None:
        self.index = (self.index + d) % len(self.names)

    def step_anim(self, d: int) -> None:
        self.anim_index = (self.anim_index + d) % len(self.anims)
        self.frame_index = 0

    def step_frame(self, d: int) -> None:
        poses = self.anims[self.anim_index][1][2]
        self.frame_index = (self.frame_index + d) % len(poses)

    def _changed(self) -> None:
        self.dirty = True
        self._renderer = PuppetRenderer(self.parts)

    # -- drawing ---------------------------------------------------------

    def compose(self) -> np.ndarray:
        """The full editor image (BGR)."""
        part_panel = self._draw_part_panel()
        preview = self._draw_preview()
        body_h = max(part_panel.shape[0], preview.shape[0])
        width = part_panel.shape[1] + preview.shape[1]
        img = np.full((HEADER_H + body_h, width, 3), 255, np.uint8)
        img[HEADER_H : HEADER_H + part_panel.shape[0], : part_panel.shape[1]] = part_panel
        img[HEADER_H : HEADER_H + preview.shape[0], part_panel.shape[1] :] = preview

        px, py = self.pivots()[self.current]
        anim, (_fps, _loop, poses) = self.anims[self.anim_index]
        line1 = (f"[{self.index + 1}/{len(self.names)}] {self.current}  pivot=({px:.0f},"
                 f" {py:.0f})   preview: {anim} {self.frame_index + 1}/{len(poses)}"
                 + ("   *unsaved*" if self.dirty else ""))
        line2 = "click/wasd: pivot  n/p: part  r: reset  [ ]: anim  , .: frame  S: save  q: quit"
        cv2.putText(img, line1, (10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (30, 30, 30), 1,
                    cv2.LINE_AA)
        cv2.putText(img, line2, (10, 44), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (110, 110, 110), 1,
                    cv2.LINE_AA)
        return img

    def _draw_part_panel(self) -> np.ndarray:
        panel = _checker(VIEW_H, VIEW_W)
        name = self.current
        part = self.parts[name]
        scale, ox, oy = self._view_transform()
        bx, by, bw, bh = layout.PARTS[name]["box"]
        cv2.rectangle(panel, (ox, oy), (ox + int(bw * scale), oy + int(bh * scale)),
                      (190, 190, 190), 1)

        h, w = part.rgba.shape[:2]
        sw, sh = max(int(w * scale), 1), max(int(h * scale), 1)
        scaled = cv2.resize(part.rgba, (sw, sh), interpolation=cv2.INTER_AREA)
        _over(panel, scaled, ox + int((part.origin[0] - bx) * scale),
              oy + int((part.origin[1] - by) * scale))

        # Template's printed cross (gray) vs the pivot in effect (red).
        tx, ty = layout.PARTS[name]["pivot"]
        tpt = (ox + int((tx - bx) * scale), oy + int((ty - by) * scale))
        cv2.drawMarker(panel, tpt, (170, 170, 170), cv2.MARKER_CROSS, 18, 1)
        px, py = self.pivots()[name]
        ppt = (ox + int((px - bx) * scale), oy + int((py - by) * scale))
        cv2.drawMarker(panel, ppt, (40, 40, 220), cv2.MARKER_CROSS, 28, 2)
        cv2.circle(panel, ppt, 9, (40, 40, 220), 1, cv2.LINE_AA)
        return panel

    def _draw_preview(self) -> np.ndarray:
        pw, ph = FRAME_W * PREVIEW_SCALE, FRAME_H * PREVIEW_SCALE
        panel = _checker(ph, pw, 12)
        pose = self.anims[self.anim_index][1][2][self.frame_index]
        frame = np.array(self._renderer.render_frame(pose))
        frame = cv2.resize(frame, (pw, ph), interpolation=cv2.INTER_NEAREST)
        _over(panel, frame, 0, 0)
        ground = int(188 * PREVIEW_SCALE)
        cv2.line(panel, (0, ground), (pw, ground), (150, 180, 150), 1)
        return panel


def run(parts: dict[str, Part], character: str, rig_path: Path) -> int:
    """Interactive loop. Returns 0 (saved or nothing to save) / 1 (quit unsaved)."""
    ed = PivotEditor(parts, character)
    clicks: list[tuple[int, int]] = []

    def on_mouse(event, x, y, _flags, _param):
        if event == cv2.EVENT_LBUTTONDOWN and HEADER_H <= y < HEADER_H + VIEW_H and x < VIEW_W:
            clicks.append((x, y - HEADER_H))

    cv2.namedWindow(WINDOW, cv2.WINDOW_AUTOSIZE)
    cv2.setMouseCallback(WINDOW, on_mouse)
    keymap = {
        ord("w"): lambda: ed.nudge(0, -1), ord("s"): lambda: ed.nudge(0, 1),
        ord("a"): lambda: ed.nudge(-1, 0), ord("d"): lambda: ed.nudge(1, 0),
        ord("n"): lambda: ed.step_part(1), ord("p"): lambda: ed.step_part(-1),
        ord("r"): ed.reset,
        ord("]"): lambda: ed.step_anim(1), ord("["): lambda: ed.step_anim(-1),
        ord("."): lambda: ed.step_frame(1), ord(","): lambda: ed.step_frame(-1),
    }
    try:
        while True:
            while clicks:
                ed.click(*clicks.pop(0))
            cv2.imshow(WINDOW, ed.compose())
            key = cv2.waitKey(30) & 0xFF
            if key in (ord("q"), 27):
                break
            if cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                break
            if key == ord("S"):
                rig.save(rig_path, ed.pivots())
                ed.dirty = False
                print(f"saved -> {rig_path}")
            elif key in keymap:
                keymap[key]()
    finally:
        cv2.destroyAllWindows()
    if ed.dirty:
        print("quit with unsaved pivot changes (press S to save next time)")
        return 1
    return 0
