"""Color ball tracking stack. Run NEXT TO robot.launch.py (the driver must already be up).

    ros2 launch pidog_bringup ball_follow.launch.py
    ros2 launch pidog_bringup ball_follow.launch.py camera:=false     # camera published elsewhere
    ros2 launch pidog_bringup ball_follow.launch.py planner:=false    # only tracker + follower

Then:
    ros2 topic pub --once /speech/text std_msgs/String "data: '빨간 공 따라가'"
    ros2 topic pub --once /ball_follower/target std_msgs/String "data: 'blue:look'"
    ros2 topic pub --once /ball_follower/target std_msgs/String "data: 'stop'"
"""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    params = PathJoinSubstitution(
        [FindPackageShare('pidog_bringup'), 'config', 'ball.yaml'])

    return LaunchDescription([
        DeclareLaunchArgument('camera', default_value='true'),
        DeclareLaunchArgument('planner', default_value='true'),

        Node(package='pidog_perception', executable='camera_node', name='camera_node',
             parameters=[params], output='screen',
             condition=IfCondition(LaunchConfiguration('camera'))),
        Node(package='pidog_perception', executable='ball_tracker_node', name='ball_tracker',
             parameters=[params], output='screen'),
        Node(package='pidog_behavior', executable='ball_follower_node', name='ball_follower',
             parameters=[params], output='screen'),
        Node(package='pidog_behavior', executable='vla_planner_node', name='vla_planner',
             parameters=[params], output='screen',
             condition=IfCondition(LaunchConfiguration('planner'))),
    ])
