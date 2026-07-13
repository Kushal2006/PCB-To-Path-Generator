import sys
if sys.prefix == '/usr':
    sys.real_prefix = sys.prefix
    sys.prefix = sys.exec_prefix = '/home/kushal/Desktop/ROS2/scara_test_ros2_ws/install/scara_solder_sim'
