"""The parts-sheet template layout — single source of truth.

The template is a fixed canonical canvas. The printed sheet has a thick black
detection frame; after a photo is warped back to this canvas, every part box
is at a known position, which is what makes segmentation deterministic.

Guides (box outlines, pivot marks, labels) print in LIGHT GRAY so the ink
threshold ignores them; the artist draws in dark pen.
"""

CANVAS_W, CANVAS_H = 1600, 2200
# Outer edge of the black detection frame (thickness grows inward).
FRAME = (30, 30, 1570, 2170)
FRAME_THICKNESS = 14

GUIDE_GRAY = 205  # printed guides — above the ink threshold
INK_THRESHOLD = 120  # pixels darker than this count as drawing

# name -> dict(box=(x, y, w, h), pivot=(x, y), label)
# Pivots are where the part attaches to the skeleton:
#   head: neck (bottom-center) · torso: hip (bottom-center), neck at top-center
#   arms: shoulder (top-center) · legs: hip (top-center) · weapon: grip (center)
PARTS = {
    "head": {
        "box": (90, 140, 320, 340),
        "pivot": (250, 480),
        "label": "HEAD (chin at bottom cross)",
    },
    "torso": {
        "box": (520, 140, 340, 500),
        "pivot": (690, 640),
        "label": "TORSO (neck top, hip at bottom cross)",
    },
    "arm_front": {
        "box": (970, 140, 240, 500),
        "pivot": (1090, 150),
        "label": "FRONT ARM (shoulder at top cross, hand down)",
    },
    "arm_rear": {
        "box": (1280, 140, 240, 500),
        "pivot": (1400, 150),
        "label": "REAR ARM (shoulder at top cross, hand down)",
    },
    "leg_front": {
        "box": (90, 760, 280, 560),
        "pivot": (230, 770),
        "label": "FRONT LEG (hip at top cross, foot down)",
    },
    "leg_rear": {
        "box": (470, 760, 280, 560),
        "pivot": (610, 770),
        "label": "REAR LEG (hip at top cross, foot down)",
    },
    "weapon": {
        "box": (850, 760, 240, 1000),
        "pivot": (970, 1260),
        "label": "WEAPON (grip at center cross; leave empty if unarmed)",
    },
}

INSTRUCTIONS = [
    "KALAKAR PARTS SHEET v1  -  side view, character faces RIGHT",
    "Draw each part INSIDE its box with a DARK pen (thick, closed outlines).",
    "Put the marked joint on the small cross. Interiors will be auto-filled.",
    "Photograph flat, all four black corners visible, even light, no shadows.",
]
