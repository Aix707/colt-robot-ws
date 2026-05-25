cmake_minimum_required(VERSION 3.0.2)
project(colt_bridle)

find_package(catkin REQUIRED COMPONENTS
  colt_msgs
  cv_bridge
  geometry_msgs
  message_filters
  rospy
  sensor_msgs
  std_msgs
  tf2_ros
  tf2_msgs
  visualization_msgs
)

catkin_package(
  CATKIN_DEPENDS colt_msgs cv_bridge geometry_msgs message_filters rospy sensor_msgs std_msgs tf2_ros tf2_msgs visualization_msgs
)

catkin_install_python(
  PROGRAMS
    scripts/colt_capture_session.py
    scripts/check_online_perception.py
    scripts/detector_node.py
    scripts/pt_view_planner_node.py
    scripts/runtime_package_loader.py
    scripts/rviz_visualizer_node.py
    scripts/scene_fusion_node.py
  DESTINATION ${CATKIN_PACKAGE_BIN_DESTINATION}
)
