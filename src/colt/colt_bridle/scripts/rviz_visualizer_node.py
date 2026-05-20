#!/usr/bin/env python3
"""Convert Colt detections into RViz markers."""

import rospy
from colt_msgs.msg import Detection3DArray
from geometry_msgs.msg import Point, Quaternion, Vector3
from std_msgs.msg import ColorRGBA
from visualization_msgs.msg import Marker, MarkerArray


def color_for_detection(detection):
    if detection.role == "source_seat":
        return ColorRGBA(0.0, 0.8, 0.2, 0.85)
    if detection.role == "target_seat":
        return ColorRGBA(0.0, 0.7, 1.0, 0.85)
    if detection.role == "source_chair":
        return ColorRGBA(0.2, 0.9, 0.35, 0.55)
    if detection.role == "target_chair":
        return ColorRGBA(0.1, 0.65, 1.0, 0.55)
    if detection.class_name == "aluminum_block" and detection.geometry_constraint_passed:
        return ColorRGBA(1.0, 0.1, 0.05, 0.95)
    if detection.class_name == "aluminum_block":
        return ColorRGBA(1.0, 0.8, 0.0, 0.90)
    return ColorRGBA(0.75, 0.75, 0.75, 0.55)


def make_marker(header, detection, marker_id, marker_type, ns, scale, color):
    marker = Marker()
    marker.header = header
    marker.ns = ns
    marker.id = marker_id
    marker.type = marker_type
    marker.action = Marker.ADD
    marker.pose.position = Point(
        x=detection.pose.pose.position.x,
        y=detection.pose.pose.position.y,
        z=detection.pose.pose.position.z,
    )
    marker.pose.orientation = Quaternion(
        x=detection.pose.pose.orientation.x,
        y=detection.pose.pose.orientation.y,
        z=detection.pose.pose.orientation.z,
        w=detection.pose.pose.orientation.w,
    )
    marker.scale = scale
    marker.color = color
    marker.lifetime = rospy.Duration(1.0)
    return marker


def text_marker(header, detection, marker_id):
    marker = make_marker(
        header,
        detection,
        marker_id,
        Marker.TEXT_VIEW_FACING,
        "labels",
        Vector3(x=0.0, y=0.0, z=0.08),
        ColorRGBA(1.0, 1.0, 1.0, 0.95),
    )
    marker.pose.position.z += max(float(detection.box.size.z), 0.04) + 0.08
    marker.text = (
        f"{detection.id}\n"
        f"{detection.role} {detection.state}\n"
        f"p={detection.confidence:.2f}"
    )
    return marker


def delete_all_marker(header):
    marker = Marker()
    marker.header = header
    marker.action = Marker.DELETEALL
    return marker


class RvizVisualizer:
    def __init__(self):
        self.marker_pub = rospy.Publisher("/colt/bridle/markers", MarkerArray, queue_size=10)
        rospy.Subscriber("/colt/bridle/detections", Detection3DArray, self.detections_cb)

    def detections_cb(self, msg):
        markers = MarkerArray()
        markers.markers.append(delete_all_marker(msg.header))
        marker_id = 1
        for detection in msg.detections:
            color = color_for_detection(detection)
            center_scale = Vector3(x=0.05, y=0.05, z=0.05)
            if detection.class_name == "aluminum_block":
                center_scale = Vector3(x=0.035, y=0.035, z=0.035)

            markers.markers.append(
                make_marker(
                    msg.header,
                    detection,
                    marker_id,
                    Marker.SPHERE,
                    "centers",
                    center_scale,
                    color,
                )
            )
            marker_id += 1

            box_color = ColorRGBA(color.r, color.g, color.b, 0.22)
            markers.markers.append(
                make_marker(
                    msg.header,
                    detection,
                    marker_id,
                    Marker.CUBE,
                    "boxes",
                    detection.box.size,
                    box_color,
                )
            )
            marker_id += 1

            markers.markers.append(text_marker(msg.header, detection, marker_id))
            marker_id += 1

        self.marker_pub.publish(markers)


def main():
    rospy.init_node("colt_rviz_visualizer")
    RvizVisualizer()
    rospy.loginfo("Colt RViz visualizer publishing /colt/bridle/markers")
    rospy.spin()


if __name__ == "__main__":
    main()
