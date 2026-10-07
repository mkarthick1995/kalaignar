"""Kalaignar command line.

  python -m kalaignar template <out.png>
      Write the printable parts-sheet template.

  python -m kalaignar palette <palette.json>
      Write a starter palette (ink/fill colors per part) to edit.

  python -m kalaignar pivots <photo> --character bengal_lathi --rig rig.json
      Interactive pivot editor with a live animation preview; S saves rig.json.

  python -m kalaignar process <photo> --character bengal_lathi --out <dir>
      Full pipeline: photo -> warped canvas -> parts -> animation strips.
      Optional: --artist "Name" (ledger credit), --debug (dump stage images),
      --palette palette.json (flat-fill colors), --rig rig.json (pivot fixes),
      --smear (motion trails on fast strikes).
"""

import argparse
import sys
from pathlib import Path

import cv2
from PIL import Image

from . import export, ingest, palette, rig, segment, template


class CliError(Exception):
    pass


def _load_parts(photo_path: Path, palette_path: Path | None, rig_path: Path | None):
    """Photo -> (canvas, parts) with palette colors and rig pivots applied."""
    colors = pivots = None
    try:
        if palette_path is not None:
            colors = palette.load(palette_path)
        if rig_path is not None:
            pivots = rig.load(rig_path)
    except (OSError, palette.PaletteError, rig.RigError) as e:
        raise CliError(str(e)) from None

    photo = cv2.imread(str(photo_path))
    if photo is None:
        raise CliError(f"cannot read {photo_path}")
    try:
        canvas = ingest.warp_to_canvas(photo)
        parts = segment.extract_parts(canvas)
    except (ingest.IngestError, ValueError) as e:
        raise CliError(str(e)) from None
    print(f"parts found: {', '.join(sorted(parts))}")
    if colors is not None:
        palette.apply(parts, colors)
    if pivots is not None:
        rig.apply(parts, pivots)
    return canvas, parts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kalaignar", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_tpl = sub.add_parser("template", help="write the printable parts sheet")
    p_tpl.add_argument("out", type=Path)

    p_pal = sub.add_parser("palette", help="write a starter palette.json")
    p_pal.add_argument("out", type=Path)

    p_piv = sub.add_parser("pivots", help="interactive pivot editor -> rig.json")
    p_piv.add_argument("photo", type=Path)
    p_piv.add_argument("--character", default="bengal_lathi", help="pose set to preview")
    p_piv.add_argument("--rig", type=Path, default=Path("rig.json"),
                       help="rig file to load (if present) and save")
    p_piv.add_argument("--palette", type=Path, default=None, help="palette.json colors")

    p_proc = sub.add_parser("process", help="photo of a drawn sheet -> game assets")
    p_proc.add_argument("photo", type=Path)
    p_proc.add_argument("--character", required=True, help="pose set, e.g. bengal_lathi")
    p_proc.add_argument("--out", type=Path, required=True, help="output directory")
    p_proc.add_argument("--artist", default="team", help="credit for the asset ledger")
    p_proc.add_argument("--debug", action="store_true", help="dump intermediate images")
    p_proc.add_argument("--palette", type=Path, default=None, help="palette.json colors")
    p_proc.add_argument("--rig", type=Path, default=None, help="rig.json pivot overrides")
    p_proc.add_argument("--smear", action="store_true",
                        help="motion-trail ghosts on fast strikes (non-looping anims)")
    p_proc.add_argument(
        "--game-dir", type=Path, default=None,
        help="game repo root: also copy strips into assets/sprites/<character>/",
    )

    args = parser.parse_args(argv)

    if args.cmd == "template":
        template.save_template(str(args.out))
        print(f"template -> {args.out}")
        return 0

    if args.cmd == "palette":
        palette.save_starter(args.out)
        print(f"palette -> {args.out}")
        return 0

    try:
        if args.cmd == "pivots":
            from . import editor

            existing = args.rig if args.rig.exists() else None
            _, parts = _load_parts(args.photo, args.palette, existing)
            return editor.run(parts, args.character, args.rig)
        canvas, parts = _load_parts(args.photo, args.palette, args.rig)
    except CliError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    if args.debug:
        dbg = args.out / "debug"
        dbg.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(dbg / "canvas.png"), canvas)
        for name, part in parts.items():
            Image.fromarray(part.rgba, "RGBA").save(dbg / f"part_{name}.png")

    written = export.export_character(
        parts, args.character, args.out, args.artist, smear=args.smear
    )
    # Record the pivots actually used, so a later run (or the editor) can reuse them.
    rig_out = args.out / "rig.json"
    rig.save(rig_out, rig.canvas_pivots(parts))
    written.append(rig_out)
    for path in written:
        print(f"  -> {path}")
    print(f"done: {len(written)} files")

    if args.game_dir is not None:
        import shutil

        target = args.game_dir / "assets" / "sprites" / args.character
        target.mkdir(parents=True, exist_ok=True)
        copied = 0
        for path in written:
            if "@" in path.name and path.suffix == ".png":
                shutil.copy2(path, target / path.name)
                copied += 1
        print(f"copied {copied} strips -> {target}")
        print("now run in the game repo:")
        print("  godot --headless --path . --import")
        print("  godot --headless --path . -s res://tools/build_sprite_frames.gd")
    return 0
