"""Stage 1 — Ingest: find the template's black frame in a photo and warp the
sheet back to the canonical canvas. Deterministic: no ML, just the frame."""

import cv2
import numpy as np

from . import layout


class IngestError(RuntimeError):
    pass


def _order_corners(pts: np.ndarray) -> np.ndarray:
    """Order 4 points as top-left, top-right, bottom-right, bottom-left."""
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).ravel()
    return np.array(
        [pts[np.argmin(s)], pts[np.argmin(d)], pts[np.argmax(s)], pts[np.argmax(d)]],
        dtype=np.float32,
    )


def warp_to_canvas(photo: np.ndarray) -> np.ndarray:
    """Photo (BGR or gray) -> canonical grayscale canvas, illumination-flattened."""
    gray = cv2.cvtColor(photo, cv2.COLOR_BGR2GRAY) if photo.ndim == 3 else photo.copy()

    # Flatten uneven lighting: divide by a heavily blurred copy.
    blur = cv2.GaussianBlur(gray, (0, 0), sigmaX=31)
    flat = cv2.divide(gray, blur, scale=255)

    # Find the frame: largest 4-point contour in the dark mask.
    _, mask = cv2.threshold(flat, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        raise IngestError("no dark frame found — is the template border visible?")
    quad = None
    for c in sorted(contours, key=cv2.contourArea, reverse=True)[:5]:
        approx = cv2.approxPolyDP(c, 0.02 * cv2.arcLength(c, True), True)
        if len(approx) == 4 and cv2.contourArea(approx) > 0.2 * gray.size:
            quad = approx.reshape(4, 2).astype(np.float32)
            break
    if quad is None:
        raise IngestError("template frame not detected — retake the photo flatter")

    x0, y0, x1, y1 = layout.FRAME
    dst = np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], dtype=np.float32)
    m = cv2.getPerspectiveTransform(_order_corners(quad), dst)
    return cv2.warpPerspective(
        flat, m, (layout.CANVAS_W, layout.CANVAS_H), flags=cv2.INTER_LINEAR,
        borderValue=255,
    )
