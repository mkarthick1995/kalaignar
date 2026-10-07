"""Smear frames: motion trails for fast strikes (opt-in, `process --smear`).

Between consecutive frames of a NON-looping animation, any limb end or weapon
end that travels more than SMEAR_MIN_PX gets fading ghosts of its part drawn
at interpolated poses, behind the real frame. Frame count and timing are
unchanged, so the game's hitbox frames still line up — the smear only adds
the in-between motion the eye expects at 20 fps.
"""

import math

from PIL import Image

from .render import FRAME_H, FRAME_W, PuppetRenderer, skeleton

SMEAR_MIN_PX = 10.0  # end-point travel (frame px) that earns a smear
GHOST_STEP_PX = 8.0  # roughly one ghost per this much travel...
MAX_GHOSTS = 4  # ...capped
GHOST_ALPHA = (0.12, 0.38)  # oldest ghost -> newest ghost opacity

# Tracked end points -> the part they belong to.
TRACKED = {
    "hand_front": "arm_front",
    "hand_rear": "arm_rear",
    "foot_front": "leg_front",
    "foot_rear": "leg_rear",
}
DEFAULTS = {
    "hip_y": 118.0, "lean": 0.0, "front_arm": -0.5, "rear_arm": -2.4,
    "front_foot": 22.0, "rear_foot": -18.0, "staff_offset": 0.0, "staff_len": 116.0,
    "whip_curve": 0.0,
}

ANGLES = {"front_arm", "rear_arm", "staff_angle"}


def _lerp(key: str, va: float, vb: float, t: float) -> float:
    d = vb - va
    if key in ANGLES:  # shortest arc, so a spin never smears the long way round
        d = (d + math.pi) % math.tau - math.pi
    return va + d * t


def lerp_pose(a: dict, b: dict, t: float) -> dict:
    """Interpolate two standing poses; missing keys use the generator defaults.
    The weapon is kept only when both poses hold it."""
    out = {}
    for key, default in DEFAULTS.items():
        out[key] = _lerp(key, float(a.get(key, default)), float(b.get(key, default)), t)
    if a.get("staff_angle") is not None and b.get("staff_angle") is not None:
        out["staff_angle"] = _lerp("staff_angle", a["staff_angle"], b["staff_angle"], t)
    return out


def moving_parts(a: dict, b: dict) -> tuple[set[str], float]:
    """Parts whose end points travel more than SMEAR_MIN_PX from a to b, and
    the largest travel distance."""
    if a.get("lying", 0) > 0 or b.get("lying", 0) > 0:
        return set(), 0.0
    sa, sb = skeleton(a), skeleton(b)
    moving, travel = set(), 0.0
    for point, part in TRACKED.items():
        d = math.dist(sa[point], sb[point])
        if d > SMEAR_MIN_PX:
            moving.add(part)
            travel = max(travel, d)
    if "weapon_ends" in sa and "weapon_ends" in sb and len(sa["weapon_ends"]) == len(
        sb["weapon_ends"]
    ):
        d = max(math.dist(p, q) for p, q in zip(sa["weapon_ends"], sb["weapon_ends"]))
        if d > SMEAR_MIN_PX:
            # The hand drives the weapon: smear the arm with it.
            moving |= {"weapon", "arm_front"}
            travel = max(travel, d)
    return moving, travel


def render_frame(renderer: PuppetRenderer, prev: dict | None, pose: dict) -> Image.Image:
    """`pose`'s frame with a smear trail from `prev` (if it moved enough)."""
    frame = renderer.render_frame(pose)
    if prev is None:
        return frame
    parts, travel = moving_parts(prev, pose)
    if not parts:
        return frame
    n = max(1, min(MAX_GHOSTS, int(travel / GHOST_STEP_PX)))
    out = Image.new("RGBA", (FRAME_W, FRAME_H), (0, 0, 0, 0))
    lo, hi = GHOST_ALPHA
    for i in range(1, n + 1):  # oldest (near prev) first, so newer ghosts paint on top
        t = i / (n + 1)
        ghost = renderer.render_frame(lerp_pose(prev, pose, t), only=parts)
        opacity = lo + (hi - lo) * (i - 1) / max(n - 1, 1)
        alpha = ghost.getchannel("A").point(lambda v, k=opacity: int(v * k))
        ghost.putalpha(alpha)
        out.alpha_composite(ghost)
    out.alpha_composite(frame)
    return out


def render_animation(renderer: PuppetRenderer, poses: list[dict]) -> Image.Image:
    """Strip like PuppetRenderer.render_animation, with smears between frames."""
    strip = Image.new("RGBA", (FRAME_W * len(poses), FRAME_H), (0, 0, 0, 0))
    prev = None
    for i, pose in enumerate(poses):
        strip.paste(render_frame(renderer, prev, pose), (i * FRAME_W, 0))
        prev = pose
    return strip
