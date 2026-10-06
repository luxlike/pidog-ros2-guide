"""Color ball detector node.

Subscribes
  /camera/image_raw/compressed  sensor_msgs/CompressedImage
  /ball_follower/target         std_msgs/String   (only to highlight the target in the debug image)

Publishes
  /perception/balls                  std_msgs/String  JSON, every processed frame:
      {"stamp": 1728222222.12, "balls": [{"color": "red", "x": -0.31, "y": 0.12,
        "radius": 0.087, "area": 1530, "circularity": 0.84, ...}, ...]}
      x: -1 (left) .. +1 (right), y: -1 (top) .. +1 (bottom), radius: fraction of image width
  /perception/ball_debug/compressed  sensor_msgs/CompressedImage  (only while someone subscribes)

Parameters
  colors            string[]  colors to detect (default: all defaults)
  hsv.<color>       int[]     6 or 12 values: h_lo s_lo v_lo h_hi s_hi v_hi [...] (OpenCV HSV)
  min_radius_px, min_circularity, process_width
"""
import json
import time

import cv2
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import CompressedImage
from std_msgs.msg import String

from pidog_perception.color_detector import DEFAULT_COLORS, ColorBallDetector, parse_ranges


class BallTracker(Node):
    def __init__(self):
        super().__init__('ball_tracker')
        self.declare_parameter('colors', list(DEFAULT_COLORS.keys()))
        self.declare_parameter('min_radius_px', 6)
        self.declare_parameter('min_circularity', 0.55)
        self.declare_parameter('process_width', 320)
        self.declare_parameter('debug_jpeg_quality', 70)

        colors = {}
        for name in self.get_parameter('colors').value:
            default = [v for rng in DEFAULT_COLORS.get(name, []) for v in rng]
            if not default:
                default = [0, 0, 0, 0, 0, 0]
            p = self.declare_parameter(f'hsv.{name}', default).value
            try:
                colors[name] = parse_ranges(p)
            except ValueError as e:
                self.get_logger().error(f'hsv.{name}: {e} -> color skipped')

        self.detector = ColorBallDetector(
            colors=colors,
            min_radius_px=int(self.get_parameter('min_radius_px').value),
            min_circularity=float(self.get_parameter('min_circularity').value),
            process_width=int(self.get_parameter('process_width').value))

        self.target = None
        self.create_subscription(CompressedImage, 'camera/image_raw/compressed', self.on_image,
                                 qos_profile_sensor_data)
        self.create_subscription(String, 'ball_follower/target', self.on_target, 10)
        self.balls_pub = self.create_publisher(String, 'perception/balls', 10)
        self.debug_pub = self.create_publisher(CompressedImage, 'perception/ball_debug/compressed',
                                               qos_profile_sensor_data)
        self.frames, self.t0 = 0, time.monotonic()
        self.get_logger().info(f'ball_tracker ready, colors={list(colors.keys())}')

    def on_target(self, msg):
        t = msg.data.strip().lower()
        self.target = None if t in ('', 'stop', 'none') else t

    def on_image(self, msg):
        img = cv2.imdecode(np.frombuffer(msg.data, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            self.get_logger().warn('jpeg decode failed', throttle_duration_sec=5.0)
            return
        balls, small = self.detector.detect(img)

        stamp = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
        self.balls_pub.publish(String(data=json.dumps(
            {'stamp': round(stamp, 3), 'balls': [b.to_dict() for b in balls]})))

        if self.debug_pub.get_subscription_count() > 0:
            dbg = ColorBallDetector.draw(small, balls, self.target)
            q = int(self.get_parameter('debug_jpeg_quality').value)
            ok, buf = cv2.imencode('.jpg', dbg, [cv2.IMWRITE_JPEG_QUALITY, q])
            if ok:
                out = CompressedImage()
                out.header = msg.header
                out.format = 'jpeg'
                out.data = buf.tobytes()
                self.debug_pub.publish(out)

        self.frames += 1
        if self.frames % 150 == 0:
            fps = self.frames / (time.monotonic() - self.t0)
            self.get_logger().info(f'processing {fps:.1f} fps')


def main():
    from rclpy.executors import ExternalShutdownException

    rclpy.init()
    node = BallTracker()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
