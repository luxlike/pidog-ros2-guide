"""Follow a ball of a given color: head tracking + turn/approach with /cmd_vel.

Subscribes
  /ball_follower/target   std_msgs/String  "red"        follow (head + walk)
                                           "red:look"   head tracking only, no walking
                                           "stop"       stop following
  /perception/balls       std_msgs/String  JSON from ball_tracker_node

Publishes
  /joint_commands         std_msgs/Float64MultiArray  head only (legs/tail = NaN)
  /cmd_vel                geometry_msgs/Twist         only while turning / approaching
  /pidog/action           std_msgs/String             "wag_tail" on arrival (optional)
  /ball_follower/status   std_msgs/String             JSON {state, target, yaw, pitch, event}

Safety: nothing moves until a target is set; `max_follow_time` ends the run; when the
follower stops publishing /cmd_vel the driver watchdog stops and stands the robot.
"""
import json
import math
import time

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from std_msgs.msg import Float64MultiArray, String

from pidog_behavior.follow_controller import (
    ARRIVED, IDLE, LOST, FollowController, FollowParams)

NAN = float('nan')


class BallFollower(Node):
    def __init__(self):
        super().__init__('ball_follower')
        defaults = FollowParams()
        for name, val in vars(defaults).items():
            self.declare_parameter(name, val)
        self.declare_parameter('rate', 10.0)
        self.declare_parameter('stale_after', 0.5)      # s, ignore old detections
        self.declare_parameter('max_follow_time', 120.0)
        self.declare_parameter('wag_on_arrive', True)
        self.declare_parameter('center_head_on_stop', True)

        self.ctrl = FollowController(self.load_params())
        self.target = None
        self.started_at = 0.0
        self.ball = None             # (x, y, r) of target in latest message
        self.ball_time = 0.0
        self.last_head = None
        self.last_state = IDLE

        self.create_subscription(String, 'ball_follower/target', self.on_target, 10)
        self.create_subscription(String, 'perception/balls', self.on_balls, 10)
        self.joint_pub = self.create_publisher(Float64MultiArray, 'joint_commands', 1)
        self.cmd_pub = self.create_publisher(Twist, 'cmd_vel', 10)
        self.action_pub = self.create_publisher(String, 'pidog/action', 10)
        self.status_pub = self.create_publisher(String, 'ball_follower/status', 10)

        self.create_timer(1.0 / float(self.get_parameter('rate').value), self.tick)
        self.get_logger().info('ball_follower ready (waiting for /ball_follower/target)')

    def load_params(self):
        p = FollowParams()
        for name in vars(p):
            setattr(p, name, type(getattr(p, name))(self.get_parameter(name).value))
        return p

    # ---------- inputs ----------
    def on_target(self, msg):
        raw = msg.data.strip().lower()
        if raw in ('', 'stop', 'none', 'halt'):
            self.halt('stopped by command')
            return
        color, _, mode = raw.partition(':')
        p = self.load_params()
        p.walk = (mode != 'look') and p.walk
        self.ctrl = FollowController(p)
        self.target = color
        self.started_at = time.monotonic()
        self.ball = None
        self.ctrl.start(self.started_at)
        self.get_logger().info(f'follow target={color} walk={p.walk}')
        self.publish_status(event='started')

    def on_balls(self, msg):
        if not self.target:
            return
        try:
            data = json.loads(msg.data)
        except json.JSONDecodeError:
            return
        match = [b for b in data.get('balls', []) if b.get('color') == self.target]
        self.ball_time = time.monotonic()
        self.ball = (match[0]['x'], match[0]['y'], match[0]['radius']) if match else None

    # ---------- loop ----------
    def tick(self):
        if not self.target:
            return
        now = time.monotonic()
        if now - self.started_at > float(self.get_parameter('max_follow_time').value):
            self.halt('max_follow_time reached')
            return

        fresh = now - self.ball_time < float(self.get_parameter('stale_after').value)
        cmd = self.ctrl.update(now, self.ball if fresh else None)

        self.send_head(cmd.head_yaw, cmd.head_pitch)
        if cmd.moving:
            t = Twist()
            t.linear.x = float(cmd.vx)
            t.angular.z = float(cmd.wz)
            self.cmd_pub.publish(t)
        # not moving -> no cmd_vel -> driver watchdog stops & stands after cmd_timeout

        if 'arrived' in cmd.events and self.get_parameter('wag_on_arrive').value:
            self.action_pub.publish(String(data='wag_tail'))
        for ev in cmd.events:
            self.get_logger().info(f'[{self.target}] {ev} -> {cmd.state}')
            self.publish_status(event=ev)
        if cmd.state != self.last_state and not cmd.events:
            self.publish_status()
        self.last_state = cmd.state

        if cmd.state == LOST:
            self.halt(f'{self.target} ball not found', publish_stop=False)

    def send_head(self, yaw, pitch):
        if self.last_head and math.dist(self.last_head, (yaw, pitch)) < 0.5:
            return
        self.last_head = (yaw, pitch)
        msg = Float64MultiArray()
        msg.data = [NAN] * 8 + [float(yaw), 0.0, float(pitch)] + [NAN]
        self.joint_pub.publish(msg)

    def halt(self, reason, publish_stop=True):
        was = self.target
        self.target = None
        self.ctrl.stop()
        if publish_stop and was:
            self.cmd_pub.publish(Twist())   # zero -> driver stops stepping
        if self.get_parameter('center_head_on_stop').value and was:
            self.last_head = None
            self.send_head(0.0, 0.0)
        self.last_state = IDLE
        self.get_logger().info(f'follow ended: {reason}')
        self.status_pub.publish(String(data=json.dumps(
            {'state': IDLE, 'target': was, 'event': 'ended', 'reason': reason},
            ensure_ascii=False)))

    def publish_status(self, event=None):
        st = {'state': self.ctrl.state, 'target': self.target,
              'yaw': round(self.ctrl.yaw, 1), 'pitch': round(self.ctrl.pitch, 1)}
        if event:
            st['event'] = event
        if self.ctrl.state == ARRIVED and self.ball:
            st['radius'] = self.ball[2]
        self.status_pub.publish(String(data=json.dumps(st, ensure_ascii=False)))


def main():
    from rclpy.executors import ExternalShutdownException

    rclpy.init()
    node = BallFollower()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        try:
            node.halt('shutdown')
        except Exception:  # noqa: BLE001
            pass
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
