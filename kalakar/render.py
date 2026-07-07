"""Stage 6 — Render: pose the rigged parts and rasterize animation frames.

Frame space matches the game: 128x192, feet baseline y=188, facing right.
Rendered at 4x supersample and downscaled for smooth edges. Skeleton geometry
mirrors the game's placeholder generator so hitboxes still line up.

Part conventions (from the template):
  arms/legs  — pivot at TOP (joint), content hangs DOWN     -> natural "down"
  torso/head — pivot at BOTTOM (hip/neck), content goes UP  -> natural "up"
  weapon     — pivot at CENTER (grip), tip UP               -> natural "up", centered
"""

import math

import numpy as np
from PIL import Image

from .segment import Part

FRAME_W, FRAME_H = 128, 192
SS = 4  # supersample factor
BASELINE = 188.0
CX = 56.0
TORSO_LEN = 42.0
ARM_LEN = 32.0
HEAD_H = 34.0

## Paint order, back to front.
Z_ORDER = ["leg_rear", "arm_rear", "torso", "head", "leg_front", "weapon", "arm_front"]

NATURAL = {
    "head": "up",
    "torso": "up",
    "weapon": "up",
    "arm_front": "down",
    "arm_rear": "down",
    "leg_front": "down",
    "leg_rear": "down",
}


class PuppetRenderer:
    def __init__(self, parts: dict[str, Part]):
        self._parts = {name: Image.fromarray(p.rgba, "RGBA") for name, p in parts.items()}
        self._pivots = {name: p.pivot for name, p in parts.items()}

    def render_animation(self, poses: list[dict]) -> Image.Image:
        """Render a horizontal strip, one frame per pose."""
        strip = Image.new("RGBA", (FRAME_W * len(poses), FRAME_H), (0, 0, 0, 0))
        for i, pose in enumerate(poses):
            strip.paste(self.render_frame(pose), (i * FRAME_W, 0))
        return strip

    def render_frame(self, pose: dict) -> Image.Image:
        canvas = Image.new("RGBA", (FRAME_W * SS, FRAME_H * SS), (0, 0, 0, 0))
        if pose.get("lying", 0) > 0:
            self._draw_lying(canvas)
        else:
            self._draw_standing(canvas, pose)
        return canvas.resize((FRAME_W, FRAME_H), Image.LANCZOS)

    # -- pose geometry (mirrors the game generator) ------------------------

    def _draw_standing(self, canvas: Image.Image, pose: dict) -> None:
        hip_y = float(pose.get("hip_y", 118.0))
        lean = float(pose.get("lean", 0.0))
        hip = (CX + lean * 10.0, hip_y)
        neck = (hip[0] + lean * 16.0, hip[1] - TORSO_LEN)
        shoulder = (neck[0], neck[1] + 5.0)
        front_arm = float(pose.get("front_arm", -0.5))
        rear_arm = float(pose.get("rear_arm", -2.4))
        front_foot = (CX + float(pose.get("front_foot", 22.0)), BASELINE)
        rear_foot = (CX + float(pose.get("rear_foot", -18.0)), BASELINE)

        hands = {}
        for key, ang in (("front", front_arm), ("rear", rear_arm)):
            hands[key] = (
                shoulder[0] + math.cos(ang) * ARM_LEN,
                shoulder[1] - math.sin(ang) * ARM_LEN,
            )

        placements = {
            "leg_rear": self._span("leg_rear", hip, rear_foot),
            "leg_front": self._span("leg_front", hip, front_foot),
            "torso": self._span("torso", hip, neck),
            "head": self._span("head", neck, (neck[0] + lean * 6.0, neck[1] - HEAD_H)),
            "arm_rear": self._span("arm_rear", shoulder, hands["rear"]),
            "arm_front": self._span("arm_front", shoulder, hands["front"]),
        }
        if "weapon" in self._parts and pose.get("staff_angle") is not None:
            a = float(pose["staff_angle"])
            hand = (
                hands["front"][0] + float(pose.get("staff_offset", 0.0)),
                hands["front"][1],
            )
            placements["weapon"] = self._weapon(hand, a, float(pose.get("staff_len", 116.0)))

        for name in Z_ORDER:
            placed = placements.get(name)
            if placed is not None:
                img, pos = placed
                canvas.alpha_composite(img, pos)

    def _draw_lying(self, canvas: Image.Image) -> None:
        """Knockdown: torso + head laid along the ground."""
        ground = BASELINE - 12.0
        left = CX - 36.0
        torso = self._span("torso", (left, ground), (left + 58.0, ground + 0.01))
        head = self._span("head", (left, ground), (left - 26.0, ground + 0.01))
        for placed in (torso, head):
            if placed is not None:
                canvas.alpha_composite(placed[0], placed[1])

    # -- part transform core -------------------------------------------------

    def _span(self, name: str, joint: tuple, target: tuple):
        """Place `name` so its pivot sits on `joint` and its content spans to
        `target` (scaled + rotated). Honors the part's natural direction."""
        if name not in self._parts:
            return None
        dx, dy = target[0] - joint[0], target[1] - joint[1]
        length = math.hypot(dx, dy)
        if length < 1e-3:
            return None
        src = self._parts[name]
        px, py = self._pivots[name]
        if NATURAL[name] == "down":
            span = max(src.height - py, 1.0)
            angle = math.degrees(math.atan2(dx, dy))
        else:  # natural "up"
            span = max(py, 1.0)
            angle = math.degrees(math.atan2(-dx, -dy))
        return self._transform(src, (px, py), length / span, angle, joint)

    def _weapon(self, grip: tuple, angle_rad: float, length: float):
        """Weapon: pivot at grip center, full drawn height maps to `length`."""
        if "weapon" not in self._parts:
            return None
        src = self._parts["weapon"]
        px, py = self._pivots["weapon"]
        # Staff direction in game space: (cos a, -sin a); natural is up (0,-1).
        angle = math.degrees(math.atan2(-math.cos(angle_rad), -(-math.sin(angle_rad))))
        return self._transform(src, (px, py), length / max(src.height, 1), angle, grip)

    def _transform(self, src: Image.Image, pivot: tuple, scale: float,
                   angle_deg: float, joint: tuple):
        scale *= SS
        w, h = max(int(src.width * scale), 1), max(int(src.height * scale), 1)
        img = src.resize((w, h), Image.LANCZOS)
        pvt = (pivot[0] * scale, pivot[1] * scale)
        img = img.rotate(angle_deg, center=pvt, expand=True, resample=Image.BICUBIC)
        # expand=True shifts the origin so the rotated bbox fits; the pivot
        # (the rotation center) moves by minus the bbox minimum. Recompute it.
        theta = math.radians(angle_deg)
        cos_t, sin_t = math.cos(theta), math.sin(theta)
        min_x, min_y = 0.0, 0.0
        for cx, cy in ((0, 0), (w, 0), (w, h), (0, h)):
            dx, dy = cx - pvt[0], cy - pvt[1]
            rx = dx * cos_t + dy * sin_t
            ry = -dx * sin_t + dy * cos_t
            min_x = min(min_x, pvt[0] + rx)
            min_y = min(min_y, pvt[1] + ry)
        pvt_new = (pvt[0] - min_x, pvt[1] - min_y)
        pos = (round(joint[0] * SS - pvt_new[0]), round(joint[1] * SS - pvt_new[1]))
        return img, pos
