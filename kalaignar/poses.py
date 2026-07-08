"""The pose library — per-frame joint poses, ported from the game's proven
placeholder generator (warriors-art tools/generate_placeholder_sprites.py).
Geometry matches gameplay: reach distances line up with authored hitboxes.

A pose dict may set: hip_y, lean, front_arm, rear_arm (radians; 0 = forward,
positive = up), front_foot, rear_foot (x offsets), staff_angle, staff_offset,
staff_len, lying (0/1). Animations: name -> (fps, loop, [poses])."""


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def lathiyal() -> dict:
    """Bengal Lathi Khela moveset poses (staff fighter)."""
    s = {"staff_angle": 1.15, "staff_len": 116.0}
    idle = [dict(hip_y=118 + b, front_arm=-0.6, **s) for b in (0, 2, 3, 2)]
    walk = [
        dict(
            hip_y=116 + (2 if i % 3 == 0 else 0),
            front_foot=_lerp(30, -6, (i % 3) / 2.0),
            rear_foot=_lerp(-26, 8, (i % 3) / 2.0),
            **s,
        )
        for i in range(6)
    ]
    jab = [
        dict(staff_angle=0.9, staff_len=116.0, front_arm=-0.5),
        dict(staff_angle=0.15, staff_len=116.0, front_arm=-0.1, staff_offset=14, lean=0.25),
        dict(staff_angle=0.0, staff_len=116.0, front_arm=0.0, staff_offset=30, lean=0.4),
        dict(staff_angle=0.35, staff_len=116.0, front_arm=-0.3, staff_offset=10, lean=0.2),
    ]
    hit = [
        dict(lean=-0.45, front_arm=1.8, rear_arm=1.4, staff_angle=1.5, staff_len=116.0),
        dict(lean=-0.6, front_arm=2.0, rear_arm=1.7, staff_angle=1.7, staff_len=116.0, hip_y=122),
    ]
    jump = [
        dict(hip_y=112, front_foot=12, rear_foot=-10, **s),
        dict(hip_y=104, front_foot=6, rear_foot=-4, **s),
        dict(hip_y=112, front_foot=14, rear_foot=-12, **s),
    ]
    crouch = [
        dict(hip_y=146, front_foot=30, rear_foot=-24, staff_angle=1.3, staff_len=116.0),
        dict(hip_y=148, front_foot=30, rear_foot=-24, staff_angle=1.3, staff_len=116.0),
    ]
    knockdown = [
        dict(lean=-0.8, hip_y=140, front_arm=2.2, rear_arm=1.9),
        dict(lying=1.0),
        dict(lying=1.0),
    ]
    return {
        "idle": (8, True, idle),
        "walk": (10, True, walk),
        "jab": (20, False, jab),
        "hit": (12, False, hit),
        "jump": (8, True, jump),
        "crouch": (8, True, crouch),
        "knockdown": (10, False, knockdown),
    }


## Character name -> pose-set factory. New movesets get added here (or, later,
## loaded from the game repo directly so there is one source of truth).
CHARACTER_POSES = {
    "bengal_lathi": lathiyal,
}
