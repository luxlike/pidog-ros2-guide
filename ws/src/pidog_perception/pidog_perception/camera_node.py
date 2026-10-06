"""Camera publisher for PiDog.

Publishes
  /camera/image_raw/compressed   sensor_msgs/CompressedImage (jpeg)

Sources (parameter `source`)
  mjpeg     (default) read the MJPEG stream served by scripts/camera_stream.py on the HOST.
            The Pi 5 CSI camera needs libcamera/picamera2, which ships with Raspberry Pi OS
            but not with the Ubuntu-based ROS container, so the host owns the camera and
            the container only reads JPEG frames (passed through without re-encoding).
  v4l2      USB webcam through OpenCV (`device` parameter, e.g. 0 or /dev/video0)
  picamera2 only if picamera2 is importable inside the container
"""
import threading
import time
import urllib.request

import cv2
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import CompressedImage


class CameraNode(Node):
    def __init__(self):
        super().__init__('camera_node')
        self.declare_parameter('source', 'mjpeg')
        self.declare_parameter('url', 'http://127.0.0.1:8081/stream.mjpg')
        self.declare_parameter('device', '0')
        self.declare_parameter('width', 640)
        self.declare_parameter('height', 480)
        self.declare_parameter('fps', 15.0)
        self.declare_parameter('jpeg_quality', 80)
        self.declare_parameter('frame_id', 'camera_link')

        self.pub = self.create_publisher(CompressedImage, 'camera/image_raw/compressed',
                                         qos_profile_sensor_data)
        self.lock = threading.Lock()
        self.latest = None          # latest jpeg bytes
        self.latest_seq = 0
        self.sent_seq = 0
        self.running = True

        src = self.get_parameter('source').value
        target = {'mjpeg': self.loop_mjpeg, 'v4l2': self.loop_v4l2,
                  'picamera2': self.loop_picamera2}.get(src)
        if target is None:
            raise ValueError(f'unknown camera source "{src}"')
        self.thread = threading.Thread(target=self.reader_wrapper, args=(target,), daemon=True)
        self.thread.start()

        fps = float(self.get_parameter('fps').value)
        self.create_timer(1.0 / max(fps, 1.0), self.publish_latest)
        self.get_logger().info(f'camera_node started (source={src})')

    # ---------- readers (background thread) ----------
    def store(self, jpeg_bytes):
        with self.lock:
            self.latest = jpeg_bytes
            self.latest_seq += 1

    def encode(self, bgr):
        q = int(self.get_parameter('jpeg_quality').value)
        ok, buf = cv2.imencode('.jpg', bgr, [cv2.IMWRITE_JPEG_QUALITY, q])
        return buf.tobytes() if ok else None

    def reader_wrapper(self, loop):
        while self.running:
            try:
                loop()
            except Exception as e:  # noqa: BLE001
                self.get_logger().warn(f'camera read error: {e} (retry in 2 s)',
                                       throttle_duration_sec=10.0)
            time.sleep(2.0)

    def loop_mjpeg(self):
        url = self.get_parameter('url').value
        with urllib.request.urlopen(url, timeout=5) as stream:
            self.get_logger().info(f'connected to {url}')
            buf = b''
            while self.running:
                chunk = stream.read(16384)
                if not chunk:
                    raise ConnectionError('stream closed')
                buf += chunk
                # Take the newest complete JPEG in the buffer (drop stale ones)
                end = buf.rfind(b'\xff\xd9')
                if end < 0:
                    if len(buf) > 4_000_000:
                        buf = b''
                    continue
                start = buf.rfind(b'\xff\xd8', 0, end)
                if start >= 0:
                    self.store(buf[start:end + 2])
                buf = buf[end + 2:]

    def loop_v4l2(self):
        dev = self.get_parameter('device').value
        cap = cv2.VideoCapture(int(dev) if str(dev).isdigit() else dev, cv2.CAP_V4L2)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, int(self.get_parameter('width').value))
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, int(self.get_parameter('height').value))
        if not cap.isOpened():
            raise ConnectionError(f'cannot open {dev}')
        try:
            while self.running:
                ok, frame = cap.read()
                if not ok:
                    raise ConnectionError('frame grab failed')
                jpg = self.encode(frame)
                if jpg:
                    self.store(jpg)
        finally:
            cap.release()

    def loop_picamera2(self):
        from picamera2 import Picamera2  # noqa: PLC0415 (optional dependency)
        cam = Picamera2()
        size = (int(self.get_parameter('width').value), int(self.get_parameter('height').value))
        cam.configure(cam.create_video_configuration(main={'size': size, 'format': 'RGB888'}))
        cam.start()
        try:
            while self.running:
                frame = cam.capture_array()  # RGB888 in picamera2 is BGR order in memory
                jpg = self.encode(np.ascontiguousarray(frame))
                if jpg:
                    self.store(jpg)
        finally:
            cam.stop()

    # ---------- publisher ----------
    def publish_latest(self):
        with self.lock:
            if self.latest is None or self.latest_seq == self.sent_seq:
                return
            data, self.sent_seq = self.latest, self.latest_seq
        msg = CompressedImage()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = self.get_parameter('frame_id').value
        msg.format = 'jpeg'
        msg.data = data
        self.pub.publish(msg)

    def shutdown(self):
        self.running = False


def main():
    from rclpy.executors import ExternalShutdownException

    rclpy.init()
    node = CameraNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.shutdown()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
