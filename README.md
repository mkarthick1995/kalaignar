# Kalaignar — கலைஞர்

**One hand-drawn parts sheet in → hundreds of game-ready animation assets out.**

Companion tool for [Warrior's Art](https://github.com/mkarthick1995/warriors-art). You draw a character's body parts on a printed template; Kalaignar detects the sheet in a photo, extracts and cleans each part, rigs them onto the game's skeleton, poses them through the game's proven animation library, and exports sprite strips in the exact format the game consumes — plus a copyright-ledger row, because the input is your own drawing (no AI, fully yours).

Architecture: see [`KALAIGNAR_ARCHITECTURE.md` in the game repo](https://github.com/mkarthick1995/warriors-art/blob/main/docs/KALAIGNAR_ARCHITECTURE.md).

## Setup

```bash
pip install -r requirements.txt   # opencv-python, numpy, Pillow
```

## Usage

**1. Print the template:**
```bash
python -m kalaignar template parts_sheet.png
```
Print it (A4, "actual size"). Draw each body part inside its box with a **dark pen** — thick, closed outlines (interiors are auto-filled). Put the marked joint on the small cross. Side view, facing **right**. Weapon box may stay empty for unarmed fighters.

**2. Photograph** the sheet flat, in even light, all four black frame corners visible.

**3. Process:**
```bash
python -m kalaignar process photo.jpg --character bengal_lathi --out out/ --artist "Your Name"
```
Outputs `anim@FRAMESxFPS.png` strips (the game's convention), a select-screen `portrait.png`, `ledger_row.md` for the game's asset ledger, and `rig.json` (the pivots used). Add `--debug` to dump the warped canvas and each extracted part.

Optional polish:

- **Colors**: `python -m kalaignar palette palette.json` writes a starter file. Set `ink`/`fill` globally or per part, then pass `--palette palette.json`. The game multiplies sprites by each player's `body_color`, so keep fills light if you want that tint to read.
- **Pivots**: if a joint looks off (an arm hinging mid-bicep, a head floating), fix it visually:
  ```bash
  python -m kalaignar pivots photo.jpg --character bengal_lathi --rig rig.json
  ```
  Click the joint on each part (`n`/`p` switch parts, `wasd` nudges, `[` `]` and `,` `.` pick the preview animation/frame), `S` saves. Then `process ... --rig rig.json`. Pivots are stored in sheet coordinates, so the rig survives redrawing a part.
- **Smears**: `--smear` adds fading motion trails to fast strikes (non-looping animations only; frame count and timing unchanged, so hitboxes still line up).
- **Urumi / whip weapons**: draw the hilt just below the weapon cross and the flexible blade above it; poses with `whip_curve` bend the blade along the game's 8-segment curve, hilt rigid.

**4. Into the game:** copy the strips to `warriors-art/assets/sprites/<character>/`, then in the game repo:
```bash
godot --headless --path . --import
godot --headless --path . -s res://tools/build_sprite_frames.gd
```

## How it works (pipeline stages)

photo → **ingest** (find the black frame, perspective-warp to the canonical canvas, flatten lighting) → **segment** (crop known part boxes, extract ink, flood-fill enclosed interiors, tight-crop with pivot tracking) → **palette / rig** (optional recolor and pivot overrides) → **render** (puppet: scale/rotate parts around joints per pose frame, 4× supersampled; whip blades bend per segment; optional smear trails) → **export** (strips + portrait + ledger row + rig.json).

Poses live in `kalaignar/poses.py`, ported from the game's placeholder generator — geometry matches gameplay, so a Kalaignar character's jab connects exactly where the game's hitboxes expect.

## Test

```bash
python tests/run_test.py
```
Synthetic end-to-end: draws a fake character onto the template programmatically, simulates a tilted photo, and runs the whole pipeline: palette, rig, the pivot editor's logic (headless), rotation accuracy at every angle, whip bending, smears, and the CLI (33 checks).

## Status / roadmap

v0.2: template + full pipeline + **all 8 fighters, 13 animations each** (104 total), synced from the game repo via `python tools/sync_poses.py` (single source of truth — rerun when the game's poses change). `--game-dir` copies strips straight into the game.

v0.3: palette file, pivot editor + `rig.json`, bendable whip weapons (Kalari's urumi), smear frames. Also fixes a renderer bug where any part rotated more than ~70° (arms held forward, horizontal staffs, spins) rendered fully transparent.

Next: forearm/hand split for more expressive arms, per-character pose overrides.
