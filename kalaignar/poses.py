"""The pose library — per-frame joint poses for every Warrior's Art fighter.

The data itself lives in pose_data.py, GENERATED from the game repo's
placeholder generator by tools/sync_poses.py (single source of truth:
geometry there is tuned against real gameplay hitboxes). Re-run the sync
whenever the game's pose sets change.

A pose dict may set: hip_y, lean, front_arm, rear_arm (radians; 0 = forward,
positive = up), front_foot, rear_foot (x offsets), staff_angle, staff_offset,
staff_len, whip_curve (radians of bend per blade segment — Kalari's urumi),
lying (0/1). Animations: name -> (fps, loop, [poses]).
"""

from .pose_data import CHARACTER_POSES

__all__ = ["CHARACTER_POSES"]
