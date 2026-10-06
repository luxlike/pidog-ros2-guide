"""PiDog ROS 2 unified driver node.

Subscribes
  /cmd_vel          geometry_msgs/Twist          walk / turn (sign & direction only)
  /pidog/action     std_msgs/String              built-in SunFounder actions ("sit", "stand", ...)
  /joint_commands   std_msgs/Float64MultiArray   12 joint targets in DEGREES, NaN = keep current

Publishes
  /imu/data         sensor_msgs/Imu              raw SH3001 values (unit conversion TBD)
  /joint_states     sensor_msgs/JointState       COMMANDED angles in radians (servos have no feedback)

IMPORTANT: Pidog() must be created in exactly ONE process. Two processes
driving the same I2C servo controller will fight each other.
"""
import math
import threading
import time

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from sensor_msgs.msg import Imu, JointState
from std_msgs.msg import Float64MultiArray, String

from pidog import Pidog

JOINT_NAMES = [
    'lf_shoulder', 'lf_knee', 'rf_shoulder', 'rf_knee',
    'lh_shoulder', 'lh_knee', 'rh_shoulder', 'rh_knee',
    'head_yaw', 'head_roll', 'head_pitch', 'tail',
]
LIMIT = 90.0  # safety limit in degrees


def clamp(v, lo=-LIMIT, hi=LIMIT):
    return max(lo, min(hi, v))


class PidogDriver(Node):
    def __init__(self):
        super().__init__('pidog_driver')

        self.declare_parameter('walk_speed', 98)      # built-in gait speed (0-100)
        self.declare_parameter('action_speed', 80)    # built-in action speed
        self.declare_parameter('joint_speed', 100)    # direct joint control speed
        self.declare_parameter('cmd_timeout', 0.5)    # cmd_vel watchdog (s)

        self.lock = threading.Lock()
        self.mode = 'idle'            # idle | walk | action | joint
        self.cmd = Twist()
        self.last_cmd_time = 0.0

        self.get_logger().info('Initializing PiDog hardware...')
        self.dog = Pidog()
        self.dog.do_action('stand', speed=60)
        self.dog.wait_all_done()

        self.create_subscription(Twist, 'cmd_vel', self.on_cmd_vel, 10)
        self.create_subscription(String, 'pidog/action', self.on_action, 10)
        self.create_subscription(Float64MultiArray, 'joint_commands', self.on_joint, 1)

        self.js_pub = self.create_publisher(JointState, 'joint_states', 10)
        self.imu_pub = self.create_publisher(Imu, 'imu/data', 10)

        self.create_timer(0.02, self.sensor_loop)   # 50 Hz: IMU + joint_states
        self.create_timer(0.1, self.gait_loop)      # 10 Hz: gait commands

        self.get_logger().info('PiDog driver ready')

    # ---------- input callbacks ----------
    def on_cmd_vel(self, msg: Twist):
        with self.lock:
            self.cmd = msg
            self.last_cmd_time = time.monotonic()
            self.mode = 'walk'

    def on_action(self, msg: String):
        name = msg.data.strip()
        with self.lock:
            if name in ('stop', 'halt'):
                self.dog.body_stop()
                self.mode = 'idle'
                return
            try:
                self.dog.body_stop()
                self.dog.do_action(name, speed=self.get_parameter('action_speed').value)
                self.mode = 'action'
                self.get_logger().info(f'action: {name}')
            except Exception as e:  # noqa: BLE001
                self.get_logger().warn(f'unknown or failed action "{name}": {e}')

    def on_joint(self, msg: Float64MultiArray):
        if len(msg.data) != 12:
            self.get_logger().warn(f'joint_commands needs 12 values, got {len(msg.data)}')
            return
        speed = self.get_parameter('joint_speed').value
        d = list(msg.data)
        with self.lock:
            self.mode = 'joint'
            cur_legs = list(getattr(self.dog, 'leg_current_angles', [0.0] * 8))
            cur_head = list(getattr(self.dog, 'head_current_angles', [0.0] * 3))

            # NaN = keep current angle
            legs, head, tail = d[0:8], d[8:11], d[11:12]
            if not all(math.isnan(v) for v in legs):
                legs = [clamp(c if math.isnan(v) else v) for v, c in zip(legs, cur_legs)]
                self.dog.legs_move([legs], immediately=True, speed=speed)
            if not all(math.isnan(v) for v in head):
                head = [clamp(c if math.isnan(v) else v) for v, c in zip(head, cur_head)]
                self.dog.head_move([head], immediately=True, speed=speed)
            if not math.isnan(tail[0]):
                self.dog.tail_move([[clamp(tail[0])]], immediately=True, speed=speed)

    # ---------- periodic loops ----------
    def gait_loop(self):
        with self.lock:
            if self.mode != 'walk':
                return
            timeout = self.get_parameter('cmd_timeout').value
            if time.monotonic() - self.last_cmd_time > timeout:
                # Watchdog: commands stopped arriving -> stop and stand
                self.dog.body_stop()
                self.dog.do_action('stand', speed=60)
                self.mode = 'idle'
                self.get_logger().info('cmd_vel timeout -> stand')
                return

            vx, wz = self.cmd.linear.x, self.cmd.angular.z
            if abs(vx) < 1e-3 and abs(wz) < 1e-3:
                return
            if abs(wz) > abs(vx):
                action = 'turn_left' if wz > 0 else 'turn_right'
            else:
                action = 'forward' if vx > 0 else 'backward'

            # Queue the next step only after the previous one finished
            if self.dog.is_legs_done():
                self.dog.do_action(action, step_count=1,
                                   speed=self.get_parameter('walk_speed').value)

    def sensor_loop(self):
        now = self.get_clock().now().to_msg()
        try:
            ax, ay, az = self.dog.accData
            gx, gy, gz = self.dog.gyroData
            imu = Imu()
            imu.header.stamp = now
            imu.header.frame_id = 'imu_link'
            imu.linear_acceleration.x = float(ax)
            imu.linear_acceleration.y = float(ay)
            imu.linear_acceleration.z = float(az)
            imu.angular_velocity.x = float(gx)
            imu.angular_velocity.y = float(gy)
            imu.angular_velocity.z = float(gz)
            self.imu_pub.publish(imu)
        except Exception as e:  # noqa: BLE001
            self.get_logger().warn(f'IMU read failed: {e}', throttle_duration_sec=2.0)

        # PiDog servos have no position feedback -> publish COMMANDED angles
        legs = list(getattr(self.dog, 'leg_current_angles', [0.0] * 8))
        head = list(getattr(self.dog, 'head_current_angles', [0.0] * 3))
        tail = list(getattr(self.dog, 'tail_current_angles', [0.0]))
        js = JointState()
        js.header.stamp = now
        js.name = JOINT_NAMES
        js.position = [math.radians(float(a)) for a in legs + head + tail]
        self.js_pub.publish(js)

    def shutdown(self):
        self.get_logger().info('Shutting down: stop and release servos')
        try:
            self.dog.body_stop()
            self.dog.close()
        except Exception:  # noqa: BLE001
            pass


def main():
    from rclpy.executors import ExternalShutdownException

    rclpy.init()
    node = PidogDriver()
    try:
        rclpy.spin(node)
    # docker compose stop sends a signal -> ExternalShutdownException
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.shutdown()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
