"""Synthetic-image tests for the HSV ball detector (no ROS, no camera needed).

    cd ws/src/pidog_perception && python3 -m pytest test -q
"""
import cv2
import numpy as np
import pytest

from pidog_perception.color_detector import ColorBallDetector, parse_ranges

# BGR colors of "balls" drawn on a gray background
BGR = {
    'red': (30, 30, 220), 'orange': (0, 120, 250), 'yellow': (30, 220, 240),
    'green': (40, 180, 40), 'blue': (220, 90, 20), 'purple': (170, 30, 140),
}


def scene(balls, size=(480, 640), bg=(128, 128, 128), noise=8, seed=0):
    img = np.full((*size, 3), bg, np.uint8)
    for color, (cx, cy, r) in balls.items():
        cv2.circle(img, (cx, cy), r, BGR[color], -1, cv2.LINE_AA)
        # simple shading so it is not a flat disc
        cv2.circle(img, (cx - r // 3, cy - r // 3), r // 3,
                   tuple(min(255, c + 30) for c in BGR[color]), -1, cv2.LINE_AA)
    rng = np.random.default_rng(seed)
    img = np.clip(img.astype(np.int16) + rng.integers(-noise, noise, img.shape), 0, 255)
    return img.astype(np.uint8)


@pytest.mark.parametrize('color', list(BGR))
def test_each_color_detected(color):
    det = ColorBallDetector()
    balls, _ = det.detect(scene({color: (320, 240, 50)}))
    assert [b.color for b in balls] == [color]
    b = balls[0]
    assert abs(b.x) < 0.05 and abs(b.y) < 0.05
    assert b.radius == pytest.approx(50 / 640, abs=0.01)


def test_positions_and_order():
    det = ColorBallDetector()
    balls, _ = det.detect(scene({'red': (100, 240, 70), 'blue': (540, 120, 30)}))
    by = {b.color: b for b in balls}
    assert by['red'].x < -0.5 and by['blue'].x > 0.5 and by['blue'].y < 0
    assert balls[0].color == 'red'            # biggest (closest) first


def test_non_round_rejected():
    det = ColorBallDetector()
    img = np.full((480, 640, 3), 128, np.uint8)
    cv2.rectangle(img, (100, 200), (540, 230), BGR['red'], -1)   # long red bar
    balls, _ = det.detect(img)
    assert balls == []


def test_tiny_blob_rejected():
    det = ColorBallDetector(min_radius_px=6)
    balls, _ = det.detect(scene({'green': (320, 240, 4)}))
    assert balls == []


def test_red_hue_wraparound():
    # magenta-ish red (H ~ 175) must still be red
    det = ColorBallDetector()
    img = np.full((240, 320, 3), 128, np.uint8)
    cv2.circle(img, (160, 120), 40, (60, 20, 220), -1)
    balls, _ = det.detect(img)
    assert balls and balls[0].color == 'red'


def test_parse_ranges():
    assert parse_ranges([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]) == [[1, 2, 3, 4, 5, 6],
                                                                      [7, 8, 9, 10, 11, 12]]
    with pytest.raises(ValueError):
        parse_ranges([1, 2, 3])


def test_draw_runs():
    det = ColorBallDetector()
    balls, small = det.detect(scene({'yellow': (320, 240, 40)}))
    out = det.draw(small, balls, target='yellow')
    assert out.shape == small.shape
