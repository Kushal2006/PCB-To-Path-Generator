"""
SCARA solder path simulation node.

WHAT THIS NODE DOES:
1. Reads your holes.csv file (tool, diameter_mm, x_mm, y_mm).
2. Assumes theta = 0, meaning we are NOT applying any board-rotation
   calibration yet -- so PCB coordinates are used directly as robot
   coordinates. (If you later solve for theta/tx/ty, apply that
   transform to the CSV BEFORE this node reads it, or edit the
   pcb_point_to_robot_point() function below.)
3. For every hole, computes the two SCARA joint angles (shoulder,
   elbow) needed to reach that point, using standard 2-link inverse
   kinematics.
4. Publishes:
     - a JointState message (so you can drive a real/simulated arm
       or view it in RViz2 with a robot_state_publisher + URDF)
     - a Marker array so you can see the arm and target points
       directly in RViz2 even without a URDF

HOW TO RUN (on your own machine, with ROS2 installed):
    cd ~/scara_ros2_ws
    colcon build
    source install/setup.bash
    ros2 run scara_solder_sim solder_path_node --ros-args -p csv_path:=/full/path/to/holes.csv
"""

import csv
import math
import time

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import JointState
from visualization_msgs.msg import Marker, MarkerArray
from geometry_msgs.msg import Point


class ScaraSolderPathNode(Node):

    def __init__(self):
        super().__init__('scara_solder_path_node')

        # ---------------- PARAMETERS ----------------
        # You can override these when running the node, e.g.:
        #   ros2 run scara_solder_sim solder_path_node --ros-args -p link1_length:=0.15
        self.declare_parameter('csv_path', 'holes.csv')
        self.declare_parameter('link1_length', 0.15)   # meters, shoulder-to-elbow
        self.declare_parameter('link2_length', 0.12)   # meters, elbow-to-tip
        self.declare_parameter('seconds_between_holes', 1.5)
        self.declare_parameter('elbow_up', True)        # pick one of the two IK solutions

        self.csv_path = self.get_parameter('csv_path').value
        self.link1_length = self.get_parameter('link1_length').value
        self.link2_length = self.get_parameter('link2_length').value
        self.seconds_between_holes = self.get_parameter('seconds_between_holes').value
        self.elbow_up = self.get_parameter('elbow_up').value

        # ---------------- LOAD HOLES ----------------
        self.holes = self.read_holes_csv(self.csv_path)
        self.get_logger().info(f'Loaded {len(self.holes)} holes from {self.csv_path}')

        # ---------------- PUBLISHERS ----------------
        self.joint_pub = self.create_publisher(JointState, 'joint_states', 10)
        self.marker_pub = self.create_publisher(MarkerArray, 'solder_path_markers', 10)

        # publish the full list of target points once, so you can see the
        # whole planned path in RViz2 immediately
        self.publish_target_markers()

        # ---------------- STEP THROUGH HOLES ----------------
        self.current_index = 0
        self.timer = self.create_timer(self.seconds_between_holes, self.timer_callback)

    # =================================================================
    # CSV READING
    # =================================================================
    def read_holes_csv(self, path):
        """Reads holes.csv (from the excellon parser) into a plain list."""
        holes = []
        with open(path, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                holes.append({
                    'tool': row['tool'],
                    'diameter_mm': float(row['diameter_mm']),
                    'x_mm': float(row['x_mm']),
                    'y_mm': float(row['y_mm']),
                })
        return holes

    # =================================================================
    # COORDINATE TRANSFORM (theta = 0 for now)
    # =================================================================
    def pcb_point_to_robot_point(self, x_mm, y_mm):
        """
        Converts one PCB-space point (in mm) into a robot-space point
        (in meters, since ROS uses meters by convention).

        theta = 0 assumption: no rotation, no offset -- PCB coordinates
        are treated as robot coordinates directly. Once you calculate
        real theta/tx/ty values (see earlier calibration steps), replace
        this function with the full rotation + translation formula.
        """
        x_m = x_mm / 1000.0
        y_m = y_mm / 1000.0
        return x_m, y_m

    # =================================================================
    # 2-LINK INVERSE KINEMATICS
    # =================================================================
    def compute_joint_angles(self, target_x, target_y):
        """
        Standard 2-link planar inverse kinematics.
        Returns (shoulder_angle, elbow_angle) in radians, or None if the
        target point is out of reach.
        """
        l1 = self.link1_length
        l2 = self.link2_length

        distance_to_target = math.sqrt(target_x ** 2 + target_y ** 2)

        # Check reachability: can the two links possibly span this distance?
        max_reach = l1 + l2
        min_reach = abs(l1 - l2)
        if distance_to_target > max_reach or distance_to_target < min_reach:
            self.get_logger().warn(
                f'Target ({target_x:.3f}, {target_y:.3f}) is out of reach '
                f'(distance={distance_to_target:.3f}m, reachable range '
                f'{min_reach:.3f}-{max_reach:.3f}m)'
            )
            return None

        # Elbow angle, using the law of cosines
        cos_elbow = (distance_to_target ** 2 - l1 ** 2 - l2 ** 2) / (2 * l1 * l2)
        cos_elbow = max(-1.0, min(1.0, cos_elbow))  # clamp for floating point safety
        elbow_angle = math.acos(cos_elbow)

        if self.elbow_up:
            elbow_angle = -elbow_angle   # the two valid IK solutions mirror by sign

        # Shoulder angle
        target_angle = math.atan2(target_y, target_x)
        offset_angle = math.atan2(
            l2 * math.sin(elbow_angle),
            l1 + l2 * math.cos(elbow_angle)
        )
        shoulder_angle = target_angle - offset_angle

        return shoulder_angle, elbow_angle

    # =================================================================
    # MARKERS (visual targets in RViz2)
    # =================================================================
    def publish_target_markers(self):
        marker_array = MarkerArray()

        points_marker = Marker()
        points_marker.header.frame_id = 'base_link'
        points_marker.ns = 'solder_targets'
        points_marker.id = 0
        points_marker.type = Marker.SPHERE_LIST
        points_marker.action = Marker.ADD
        points_marker.scale.x = 0.004
        points_marker.scale.y = 0.004
        points_marker.scale.z = 0.004
        points_marker.color.r = 1.0
        points_marker.color.g = 0.6
        points_marker.color.b = 0.0
        points_marker.color.a = 1.0

        for hole in self.holes:
            x_m, y_m = self.pcb_point_to_robot_point(hole['x_mm'], hole['y_mm'])
            p = Point()
            p.x = x_m
            p.y = y_m
            p.z = 0.0
            points_marker.points.append(p)

        marker_array.markers.append(points_marker)
        self.marker_pub.publish(marker_array)

    def publish_arm_markers(self, shoulder_angle, elbow_angle, target_x, target_y):
        """Draws the two arm links as a line strip, so you can see the arm posture."""
        l1 = self.link1_length
        l2 = self.link2_length

        elbow_x = l1 * math.cos(shoulder_angle)
        elbow_y = l1 * math.sin(shoulder_angle)
        tip_x = elbow_x + l2 * math.cos(shoulder_angle + elbow_angle)
        tip_y = elbow_y + l2 * math.sin(shoulder_angle + elbow_angle)

        arm_marker = Marker()
        arm_marker.header.frame_id = 'base_link'
        arm_marker.ns = 'arm_links'
        arm_marker.id = 1
        arm_marker.type = Marker.LINE_STRIP
        arm_marker.action = Marker.ADD
        arm_marker.scale.x = 0.01
        arm_marker.color.r = 0.0
        arm_marker.color.g = 0.5
        arm_marker.color.b = 1.0
        arm_marker.color.a = 1.0

        origin = Point(x=0.0, y=0.0, z=0.0)
        elbow = Point(x=elbow_x, y=elbow_y, z=0.0)
        tip = Point(x=tip_x, y=tip_y, z=0.0)
        arm_marker.points = [origin, elbow, tip]

        marker_array = MarkerArray()
        marker_array.markers.append(arm_marker)
        self.marker_pub.publish(marker_array)

    # =================================================================
    # MAIN LOOP -- moves to one hole every N seconds
    # =================================================================
    def timer_callback(self):
        if self.current_index >= len(self.holes):
            self.get_logger().info('All holes visited. Stopping.')
            self.timer.cancel()
            return

        hole = self.holes[self.current_index]
        target_x, target_y = self.pcb_point_to_robot_point(hole['x_mm'], hole['y_mm'])

        result = self.compute_joint_angles(target_x, target_y)
        if result is None:
            self.get_logger().warn(f'Skipping unreachable hole #{self.current_index}')
            self.current_index += 1
            return

        shoulder_angle, elbow_angle = result

        # publish joint state for RViz2 / robot_state_publisher
        joint_state = JointState()
        joint_state.header.stamp = self.get_clock().now().to_msg()
        joint_state.name = ['shoulder_joint', 'elbow_joint']
        joint_state.position = [shoulder_angle, elbow_angle]
        self.joint_pub.publish(joint_state)

        # publish the arm posture for visualization
        self.publish_arm_markers(shoulder_angle, elbow_angle, target_x, target_y)

        self.get_logger().info(
            f'Hole #{self.current_index} tool={hole["tool"]} '
            f'target=({target_x*1000:.2f}mm, {target_y*1000:.2f}mm) -> '
            f'shoulder={math.degrees(shoulder_angle):.1f}deg '
            f'elbow={math.degrees(elbow_angle):.1f}deg'
        )

        self.current_index += 1


def main(args=None):
    rclpy.init(args=args)
    node = ScaraSolderPathNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
