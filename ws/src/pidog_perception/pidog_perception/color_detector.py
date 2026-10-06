"""HSV color ball detector (pure OpenCV/numpy, no ROS dependency -> unit-testable).

OpenCV HSV ranges: H 0-179, S 0-255, V 0-255.
Each color is one or two [h_lo, s_lo, v_lo, h_hi, s_hi, v_hi] ranges
(red wraps around H=0, so it needs two).
"""
from dataclasses import dataclass, asdict
import math

import cv2
import numpy as np

# Default ranges. Tune on the real robot with the debug image (lighting matters a lot).
DEFAULT_COLORS = {
    'red':    [[0, 120, 70, 8, 255, 255], [170, 120, 70, 179, 255, 255]],
    'orange': [[9, 120, 90, 21, 255, 255]],
    'yellow': [[22, 100, 100, 35, 255, 255]],
    'green':  [[36, 70, 50, 85, 255, 255]],
    'blue':   [[90, 110, 50, 128, 255, 255]],
    'purple': [[129, 60, 50, 160, 255, 255]],
}

# BGR colors used for drawing on the debug image
DRAW_BGR = {
    'red': (0, 0, 255), 'orange': (0, 140, 255), 'yellow': (0, 230, 255),
    'green': (0, 200, 0), 'blue': (255, 80, 0), 'purple': (200, 0, 160),
}

@dataclass
class Ball:
    color: str
    x: float          # center, normalized -1 (left) .. +1 (right)
    y: float          # center, normalized -1 (top)  .. +1 (bottom)
    radius: float     # radius / image width (0..~0.5) -> grows as the ball gets closer
    area: float       # contour area in pixels (of the processed image)
    circularity: float
    px: int = 0       # center in pixels (processed image), for drawing
    py: int = 0
    pr: int = 0

    def to_dict(self):
        d = asdict(self)
        for k in ('x', 'y', 'radius', 'circularity'):
            d[k] = round(d[k], 3)
        d['area'] = int(d['area'])
        return d


def parse_ranges(flat):
    """[a,b,c,d,e,f, a,b,...] (multiple of 6) -> [[6], [6], ...]."""
    flat = [int(v) for v in flat]
    if not flat or len(flat) % 6:
        raise ValueError(f'HSV range list must be a multiple of 6 values, got {len(flat)}')
    return [flat[i:i + 6] for i in range(0, len(flat), 6)]


class ColorBallDetector:
    def __init__(self, colors=None, min_radius_px=6, min_circularity=0.55,
                 process_width=320, blur=5):
        self.colors = dict(colors or DEFAULT_COLORS)
        self.min_radius_px = min_radius_px
        self.min_circularity = min_circularity
        self.process_width = process_width
        self.blur = blur | 1  # must be odd
        self.kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))

    def resize(self, bgr):
        h, w = bgr.shape[:2]
        if self.process_width and w > self.process_width:
            scale = self.process_width / w
            bgr = cv2.resize(bgr, (self.process_width, int(round(h * scale))),
                             interpolation=cv2.INTER_AREA)
        return bgr

    def mask(self, hsv, color):
        m = None
        for lo_hi in self.colors[color]:
            lo = np.array(lo_hi[:3], np.uint8)
            hi = np.array(lo_hi[3:], np.uint8)
            part = cv2.inRange(hsv, lo, hi)
            m = part if m is None else cv2.bitwise_or(m, part)
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, self.kernel)
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, self.kernel)
        return m

    def detect(self, bgr, colors=None):
        """Return (balls, processed_bgr). balls: largest ball per color, sorted by radius desc."""
        img = self.resize(bgr)
        h, w = img.shape[:2]
        if self.blur > 1:
            img_b = cv2.GaussianBlur(img, (self.blur, self.blur), 0)
        else:
            img_b = img
        hsv = cv2.cvtColor(img_b, cv2.COLOR_BGR2HSV)

        found = []
        for color in (colors or self.colors.keys()):
            if color not in self.colors:
                continue
            contours, _ = cv2.findContours(self.mask(hsv, color), cv2.RETR_EXTERNAL,
                                           cv2.CHAIN_APPROX_SIMPLE)
            best = None
            for c in contours:
                (cx, cy), r = cv2.minEnclosingCircle(c)
                if r < self.min_radius_px:
                    continue
                area = cv2.contourArea(c)
                circ = area / (math.pi * r * r)
                if circ < self.min_circularity:
                    continue
                if best is None or r > best.pr:
                    best = Ball(color=color,
                                x=(cx - w / 2) / (w / 2), y=(cy - h / 2) / (h / 2),
                                radius=r / w, area=area, circularity=circ,
                                px=int(cx), py=int(cy), pr=int(r))
            if best:
                found.append(best)
        found.sort(key=lambda b: b.radius, reverse=True)
        return found, img

    @staticmethod
    def draw(img, balls, target=None):
        out = img.copy()
        for b in balls:
            bgr = DRAW_BGR.get(b.color, (255, 255, 255))
            thick = 3 if b.color == target else 1
            cv2.circle(out, (b.px, b.py), b.pr, bgr, thick)
            cv2.circle(out, (b.px, b.py), 2, bgr, -1)
            cv2.putText(out, f'{b.color} r={b.radius:.2f}', (b.px - b.pr, max(12, b.py - b.pr - 4)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, bgr, 1, cv2.LINE_AA)
        h, w = out.shape[:2]
        cv2.line(out, (w // 2, 0), (w // 2, h), (200, 200, 200), 1)
        if target:
            cv2.putText(out, f'target: {target}', (4, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                        (255, 255, 255), 1, cv2.LINE_AA)
        return out

