cmake_minimum_required(VERSION 3.0.2)
project(colt_ui)

find_package(catkin REQUIRED COMPONENTS
  colt_msgs
  rospy
  std_msgs
  visualization_msgs
)

catkin_package(
  CATKIN_DEPENDS colt_msgs rospy std_msgs visualization_msgs
)

catkin_install_python(
  PROGRAMS
    scripts/terminal_chair_selector.py
    scripts/rviz_marker_publisher.py
  DESTINATION ${CATKIN_PACKAGE_BIN_DESTINATION}
)
