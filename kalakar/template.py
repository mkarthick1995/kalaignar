"""Generate the printable parts-sheet template."""

from PIL import Image, ImageDraw

from . import layout


def make_template() -> Image.Image:
    img = Image.new("L", (layout.CANVAS_W, layout.CANVAS_H), 255)
    d = ImageDraw.Draw(img)

    # Detection frame (the only DARK printed element).
    x0, y0, x1, y1 = layout.FRAME
    for t in range(layout.FRAME_THICKNESS):
        d.rectangle([x0 + t, y0 + t, x1 - t, y1 - t], outline=0)

    g = layout.GUIDE_GRAY
    for part in layout.PARTS.values():
        bx, by, bw, bh = part["box"]
        d.rectangle([bx, by, bx + bw, by + bh], outline=g, width=3)
        px, py = part["pivot"]
        d.line([px - 14, py, px + 14, py], fill=g, width=3)
        d.line([px, py - 14, px, py + 14], fill=g, width=3)
        d.ellipse([px - 7, py - 7, px + 7, py + 7], outline=g, width=2)
        d.text((bx + 6, by + bh + 8), part["label"], fill=g)

    ty = 1420
    for line in layout.INSTRUCTIONS:
        d.text((110, ty), line, fill=g)
        ty += 34
    return img


def save_template(path: str) -> None:
    make_template().save(path, dpi=(200, 200))
