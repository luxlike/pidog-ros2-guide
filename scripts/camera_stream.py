#!/usr/bin/env python3
"""HOST-side MJPEG server for the PiDog CSI camera (run on Raspberry Pi OS, NOT in Docker).

The Pi 5 camera needs libcamera + picamera2, which come with Raspberry Pi OS but are not
available in the Ubuntu-based ROS container. The host owns the camera and serves JPEG
frames; camera_node in the container reads them (network_mode: host -> 127.0.0.1).

    sudo apt install -y python3-picamera2      # usually preinstalled
    python3 scripts/camera_stream.py           # http://127.0.0.1:8081/stream.mjpg
    python3 scripts/camera_stream.py --host 0.0.0.0   # also view from a PC browser (no auth!)

Stop vilib / other camera users first: only one process can open the camera.
Run as a service: see docs/09-ball-tracking.md.
"""
import argparse
import io
import logging
import socketserver
from http import server
from threading import Condition

from picamera2 import Picamera2
from picamera2.encoders import JpegEncoder
from picamera2.outputs import FileOutput


class FrameBuffer(io.BufferedIOBase):
    def __init__(self):
        self.frame = None
        self.condition = Condition()

    def write(self, buf):
        with self.condition:
            self.frame = buf
            self.condition.notify_all()
        return len(buf)


OUTPUT = FrameBuffer()


class Handler(server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path == '/snapshot.jpg':
            with OUTPUT.condition:
                OUTPUT.condition.wait(timeout=2)
                frame = OUTPUT.frame
            self.send_response(200)
            self.send_header('Content-Type', 'image/jpeg')
            self.send_header('Content-Length', str(len(frame)))
            self.end_headers()
            self.wfile.write(frame)
            return
        if self.path != '/stream.mjpg':
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header('Cache-Control', 'no-cache, private')
        self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=FRAME')
        self.end_headers()
        try:
            while True:
                with OUTPUT.condition:
                    OUTPUT.condition.wait()
                    frame = OUTPUT.frame
                self.wfile.write(b'--FRAME\r\n')
                self.send_header('Content-Type', 'image/jpeg')
                self.send_header('Content-Length', str(len(frame)))
                self.end_headers()
                self.wfile.write(frame)
                self.wfile.write(b'\r\n')
        except (BrokenPipeError, ConnectionResetError):
            logging.info('client %s disconnected', self.client_address)


class Server(socketserver.ThreadingMixIn, server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--host', default='127.0.0.1')
    ap.add_argument('--port', type=int, default=8081)
    ap.add_argument('--width', type=int, default=640)
    ap.add_argument('--height', type=int, default=480)
    ap.add_argument('--fps', type=int, default=15)
    ap.add_argument('--quality', type=int, default=80)
    ap.add_argument('--hflip', action='store_true')
    ap.add_argument('--vflip', action='store_true')
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO)

    from libcamera import Transform
    cam = Picamera2()
    cam.configure(cam.create_video_configuration(
        main={'size': (args.width, args.height)},
        transform=Transform(hflip=args.hflip, vflip=args.vflip),
        controls={'FrameRate': args.fps}))
    cam.start_recording(JpegEncoder(q=args.quality), FileOutput(OUTPUT))
    logging.info('serving http://%s:%d/stream.mjpg', args.host, args.port)
    try:
        Server((args.host, args.port), Handler).serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        cam.stop_recording()


if __name__ == '__main__':
    main()
