"""Kalaignar command line.

  python -m kalaignar template <out.png>
      Write the printable parts-sheet template.

  python -m kalaignar process <photo> --character bengal_lathi --out <dir>
      Full pipeline: photo -> warped canvas -> parts -> animation strips.
      Optional: --artist "Name" (ledger credit), --debug (dump stage images).
"""

import argparse
import sys
from pathlib import Path

import cv2
from PIL import Image

from . import export, ingest, segment, template


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kalaignar", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_tpl = sub.add_parser("template", help="write the printable parts sheet")
    p_tpl.add_argument("out", type=Path)

    p_proc = sub.add_parser("process", help="photo of a drawn sheet -> game assets")
    p_proc.add_argument("photo", type=Path)
    p_proc.add_argument("--character", required=True, help="pose set, e.g. bengal_lathi")
    p_proc.add_argument("--out", type=Path, required=True, help="output directory")
    p_proc.add_argument("--artist", default="team", help="credit for the asset ledger")
    p_proc.add_argument("--debug", action="store_true", help="dump intermediate images")

    args = parser.parse_args(argv)

    if args.cmd == "template":
        template.save_template(str(args.out))
        print(f"template -> {args.out}")
        return 0

    photo = cv2.imread(str(args.photo))
    if photo is None:
        print(f"cannot read {args.photo}", file=sys.stderr)
        return 1
    canvas = ingest.warp_to_canvas(photo)
    parts = segment.extract_parts(canvas)
    print(f"parts found: {', '.join(sorted(parts))}")

    if args.debug:
        dbg = args.out / "debug"
        dbg.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(dbg / "canvas.png"), canvas)
        for name, part in parts.items():
            Image.fromarray(part.rgba, "RGBA").save(dbg / f"part_{name}.png")

    written = export.export_character(parts, args.character, args.out, args.artist)
    for path in written:
        print(f"  -> {path}")
    print(f"done: {len(written)} files")
    return 0
