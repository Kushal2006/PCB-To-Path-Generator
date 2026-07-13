"""
Launch file: starts the solder path node.

Run with:
    ros2 launch scara_solder_sim solder_sim.launch.py csv_path:=/full/path/to/holes.csv

Then, in a separate terminal, open RViz2 and add:
    - a MarkerArray display, topic /solder_path_markers
    - (optional) a JointState / TF setup if you build a URDF later
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    csv_path_arg = DeclareLaunchArgument(
        'csv_path',
        default_value='holes.csv',
        description='Path to the holes.csv file produced by the excellon parser'
    )

    solder_node = Node(
        package='scara_solder_sim',
        executable='solder_path_node',
        name='scara_solder_path_node',
        output='screen',
        parameters=[{
            'csv_path': LaunchConfiguration('csv_path'),
            'link1_length': 0.15,
            'link2_length': 0.12,
            'seconds_between_holes': 1.5,
            'elbow_up': True,
        }]
    )

    return LaunchDescription([csv_path_arg, solder_node])
