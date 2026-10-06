"""Bring up the PiDog robot stack.

    ros2 launch pidog_bringup robot.launch.py                 # driver + rosbridge + web
    ros2 launch pidog_bringup robot.launch.py rosbridge:=false  # on untrusted networks
"""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import AnyLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    params = PathJoinSubstitution(
        [FindPackageShare('pidog_bringup'), 'config', 'pidog.yaml'])

    rosbridge_launch = PathJoinSubstitution(
        [FindPackageShare('rosbridge_server'), 'launch', 'rosbridge_websocket_launch.xml'])

    return LaunchDescription([
        DeclareLaunchArgument('rosbridge', default_value='true',
                              description='Start rosbridge websocket server'),
        DeclareLaunchArgument('rosbridge_port', default_value='9090'),
        DeclareLaunchArgument('web', default_value='true',
                              description='Serve /ws/web on port 8080'),

        Node(
            package='pidog_driver',
            executable='driver_node',
            name='pidog_driver',
            parameters=[params],
            output='screen',
            respawn=True,          # restart 3 s after a crash
            respawn_delay=3.0,
        ),

        IncludeLaunchDescription(
            AnyLaunchDescriptionSource(rosbridge_launch),
            launch_arguments={'port': LaunchConfiguration('rosbridge_port')}.items(),
            condition=IfCondition(LaunchConfiguration('rosbridge')),
        ),

        ExecuteProcess(
            cmd=['python3', '-m', 'http.server', '8080', '-d', '/ws/web'],
            output='log',
            condition=IfCondition(LaunchConfiguration('web')),
        ),
    ])
