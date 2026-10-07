"""Stage 6 — Render: pose the rigged parts and rasterize animation frames.

Frame space matches the game: 128x192, feet baseline y=188, facing right.
Rendered at 4x supersample and downscaled for smooth edges. Skeleton geometry
mirrors the game's placeholder generator so hitboxes still line up.

Part conventions (from the template):
  arms/legs  — pivot at TOP (joint), content hangs DOWN     -> natural "down"
  torso/head — pivot at BOTTOM (hip/neck), content goes UP  -> natural "up"
  weapon     — pivot at CENTER (grip), tip UP               -> natural "up", centered

Whip weapons (pose has whip_curve, e.g. Kalari's urumi): the blade ABOVE the
grip is cut into WHIP_SEGMENTS bands chained from the hand, each turned
whip_curve further than the last — the game generator's exact polyline. The
part below the grip (hilt) stays rigid.
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
WHIP_SEGMENTS = 8  # matches the game generator's urumi polyline
WHIP_OVERLAP = 0.25  # each band reaches this fraction into the previous one (no gaps)

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


def _up_to(angle_rad: float) -> float:
    """Rotation (degrees, PIL convention) turning a part's natural "up" toward
    game-space direction (cos a, -sin a)."""
    return math.degrees(math.atan2(-math.cos(angle_rad), math.sin(angle_rad)))


def skeleton(pose: dict) -> dict:
    """Joint positions (frame space) for a standing pose — the game generator's
    geometry. Includes "grip" and "weapon_ends" when the pose holds a weapon."""
    lean = float(pose.get("lean", 0.0))
    hip = (CX + lean * 10.0, float(pose.get("hip_y", 118.0)))
    neck = (hip[0] + lean * 16.0, hip[1] - TORSO_LEN)
    shoulder = (neck[0], neck[1] + 5.0)
    sk = {"lean": lean, "hip": hip, "neck": neck, "shoulder": shoulder,
          "foot_front": (CX + float(pose.get("front_foot", 22.0)), BASELINE),
          "foot_rear": (CX + float(pose.get("rear_foot", -18.0)), BASELINE)}
    for key, default in (("front", -0.5), ("rear", -2.4)):
        ang = float(pose.get(f"{key}_arm", default))
        sk[f"hand_{key}"] = (shoulder[0] + math.cos(ang) * ARM_LEN,
                             shoulder[1] - math.sin(ang) * ARM_LEN)
    if pose.get("staff_angle") is not None:
        grip = (sk["hand_front"][0] + float(pose.get("staff_offset", 0.0)),
                sk["hand_front"][1])
        a, length = float(pose["staff_angle"]), float(pose.get("staff_len", 116.0))
        curve = float(pose.get("whip_curve", 0.0))
        if curve != 0.0:  # tip of the generator's 8-segment polyline
            x, y, ang = grip[0], grip[1], a
            for _ in range(WHIP_SEGMENTS):
                x, y = x + math.cos(ang) * length / WHIP_SEGMENTS,                     y - math.sin(ang) * length / WHIP_SEGMENTS
                ang -= curve
            ends = [(x, y)]
        else:  # staff held through the hand: both ends
            dx, dy = math.cos(a) * length / 2, -math.sin(a) * length / 2
            ends = [(grip[0] + dx, grip[1] + dy), (grip[0] - dx, grip[1] - dy)]
        sk["grip"], sk["weapon_ends"] = grip, ends
    return sk


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

    def render_frame(self, pose: dict, only: set[str] | None = None) -> Image.Image:
        """One 128x192 frame. `only` limits drawing to those parts (smears)."""
        canvas = Image.new("RGBA", (FRAME_W * SS, FRAME_H * SS), (0, 0, 0, 0))
        if pose.get("lying", 0) > 0:
            self._draw_lying(canvas)
        else:
            self._draw_standing(canvas, pose, only)
        return canvas.resize((FRAME_W, FRAME_H), Image.LANCZOS)

    # -- pose geometry (mirrors the game generator) ------------------------

    def _draw_standing(self, canvas: Image.Image, pose: dict,
                       only: set[str] | None = None) -> None:
        sk = skeleton(pose)
        hip, neck, shoulder, lean = sk["hip"], sk["neck"], sk["shoulder"], sk["lean"]
        placements = {
            "leg_rear": lambda: self._span("leg_rear", hip, sk["foot_rear"]),
            "leg_front": lambda: self._span("leg_front", hip, sk["foot_front"]),
            "torso": lambda: self._span("torso", hip, neck),
            "head": lambda: self._span(
                "head", neck, (neck[0] + lean * 6.0, neck[1] - HEAD_H)),
            "arm_rear": lambda: self._span("arm_rear", shoulder, sk["hand_rear"]),
            "arm_front": lambda: self._span("arm_front", shoulder, sk["hand_front"]),
        }
        if "grip" in sk:
            a, length = float(pose["staff_angle"]), float(pose.get("staff_len", 116.0))
            curve = float(pose.get("whip_curve", 0.0))
            if curve != 0.0:
                placements["weapon"] = lambda: self._whip(sk["grip"], a, curve, length)
            else:
                placements["weapon"] = lambda: self._weapon(sk["grip"], a, length)

        for name in Z_ORDER:
            if name not in placements or (only is not None and name not in only):
                continue
            placed = placements[name]()
            if placed is None:
                continue
            for img, pos in placed if isinstance(placed, list) else [placed]:
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
        return self._transform(src, (px, py), length / max(src.height, 1),
                               _up_to(angle_rad), grip)

    def _whip(self, grip: tuple, angle_rad: float, curve: float, length: float):
        """Flexible blade: the drawing above the grip maps to `length`, cut into
        bands that follow the generator's curving polyline from the hand.
        Returns a list of (img, pos), hilt first."""
        if "weapon" not in self._parts:
            return None
        src = self._parts["weapon"]
        px, py = self._pivots["weapon"]
        if py < WHIP_SEGMENTS * 2:  # grip drawn at the very top: nothing to bend
            return self._weapon(grip, angle_rad, length)
        blade_h = min(py, src.height)
        scale = length / blade_h
        out = []
        if py < src.height:  # hilt: below the grip, rigid, continuing behind the hand
            hilt = src.crop((0, int(py), src.width, src.height))
            out.append(self._transform(hilt, (px, 0.0), scale, _up_to(angle_rad), grip))

        band = blade_h / WHIP_SEGMENTS
        seg_len = length / WHIP_SEGMENTS
        joint, ang = grip, angle_rad
        for k in range(WHIP_SEGMENTS):
            bottom = blade_h - k * band
            top = max(bottom - band, 0.0)
            reach = min(bottom + band * WHIP_OVERLAP, src.height)
            piece = src.crop((0, int(top), src.width, math.ceil(reach)))
            out.append(self._transform(piece, (px, bottom - int(top)), scale,
                                       _up_to(ang), joint))
            joint = (joint[0] + math.cos(ang) * seg_len, joint[1] - math.sin(ang) * seg_len)
            ang -= curve
        return out

    def _transform(self, src: Image.Image, pivot: tuple, scale: float,
                   angle_deg: float, joint: tuple):
        scale *= SS
        w, h = max(int(src.width * scale), 1), max(int(src.height * scale), 1)
        img = src.resize((w, h), Image.LANCZOS)
        pvt = (pivot[0] * scale, pivot[1] * scale)
        # Rotate about the image CENTER: Pillow's expand=True combined with an
        # off-center `center=` crops the content away past ~70° (limbs held
        # horizontal vanished). Then locate the pivot analytically: rotate its
        # offset from the center (counter-clockwise on screen, y down).
        img = img.rotate(angle_deg, expand=True, resample=Image.BICUBIC)
        theta = math.radians(angle_deg)
        cos_t, sin_t = math.cos(theta), math.sin(theta)
        dx, dy = pvt[0] - w / 2, pvt[1] - h / 2
        pvt_new = (
            img.width / 2 + dx * cos_t + dy * sin_t,
            img.height / 2 - dx * sin_t + dy * cos_t,
        )
        pos = (round(joint[0] * SS - pvt_new[0]), round(joint[1] * SS - pvt_new[1]))
        return img, pos
