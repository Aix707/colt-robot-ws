cmake_minimum_required(VERSION 3.0.2)
project(colt_bridle)

find_package(catkin REQUIRED COMPONENTS
  colt_msgs
  geometry_msgs
  rospy
  std_msgs
  visualization_msgs
)

catkin_package(
  CATKIN_DEPENDS colt_msgs geometry_msgs rospy std_msgs visualization_msgs
)

catkin_install_python(
  PROGRAMS
    scripts/fake_scene_publisher.py
  DESTINATION ${CATKIN_PACKAGE_BIN_DESTINATION}
)
