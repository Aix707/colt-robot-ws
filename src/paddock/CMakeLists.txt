cmake_minimum_required(VERSION 3.0.2)
project(paddock)

find_package(catkin REQUIRED COMPONENTS
  colt_msgs
  rospy
  std_msgs
  tf2_ros
)

catkin_package(
  CATKIN_DEPENDS colt_msgs rospy std_msgs tf2_ros
)

catkin_install_python(
  PROGRAMS
    scripts/telemetry_uploader.py
  DESTINATION ${CATKIN_PACKAGE_BIN_DESTINATION}
)
