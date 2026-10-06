"""Minimal IMU-only node, used as the first hardware smoke test.

Do NOT run this together with driver_node: both create Pidog(), and only one
process may own the servo controller. driver_node already publishes /imu/data.
"""
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Imu

from pidog import Pidog


class ImuNode(Node):
    def __init__(self):
        super().__init__('pidog_imu')
        self.dog = Pidog()
        self.pub = self.create_publisher(Imu, 'imu/data', 10)
        self.create_timer(0.02, self.tick)   # 50 Hz
        self.get_logger().info('PiDog IMU node started')

    def tick(self):
        try:
            ax, ay, az = self.dog.accData
            gx, gy, gz = self.dog.gyroData
        except Exception as e:  # noqa: BLE001
            self.get_logger().warn(f'IMU read failed: {e}')
            return
        msg = Imu()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = 'imu_link'
        # Raw values (unit conversion to m/s^2, rad/s TBD)
        msg.linear_acceleration.x = float(ax)
        msg.linear_acceleration.y = float(ay)
        msg.linear_acceleration.z = float(az)
        msg.angular_velocity.x = float(gx)
        msg.angular_velocity.y = float(gy)
        msg.angular_velocity.z = float(gz)
        self.pub.publish(msg)

    def destroy_node(self):
        self.dog.close()
        super().destroy_node()


def main():
    rclpy.init()
    node = ImuNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
