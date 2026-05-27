#!/usr/bin/env python3
"""Simple RViz markers for Colt detections."""

import rospy
from colt_msgs.msg import Detection3D, Detection3DArray
from std_msgs.msg import String
from visualization_msgs.msg import Marker, MarkerArray


class RVizMarkerPublisher:
    def __init__(self):
        self.source_chair = ""
        self.target_chair = ""
        self.marker_topic = rospy.get_param("~marker_topic", "/colt/ui/rviz_markers")
        self.marker_lifetime = float(rospy.get_param("~marker_lifetime_sec", 1.0))
        self.chair_scale = float(rospy.get_param("~chair_scale", 0.40))
        self.seat_height = float(rospy.get_param("~seat_height", 0.05))
        self.item_scale = float(rospy.get_param("~item_scale", 0.06))

        self.marker_pub = rospy.Publisher(self.marker_topic, MarkerArray, queue_size=1)
        rospy.Subscriber("/colt/ui/selected_source_chair", String, self.source_cb, queue_size=1)
        rospy.Subscriber("/colt/ui/selected_target_chair", String, self.target_cb, queue_size=1)
        rospy.Subscriber("/colt/bridle/detections", Detection3DArray, self.detections_cb, queue_size=1)

    def source_cb(self, msg):
        self.source_chair = msg.data.strip()

    def target_cb(self, msg):
        self.target_chair = msg.data.strip()

    def detections_cb(self, msg):
        markers = MarkerArray()
        marker_id = 0

        for detection in msg.detections:
            if int(detection.state) == Detection3D.STATE_LOST:
                continue

            if detection.object_type == "chair":
                markers.markers.extend(self.chair_markers(detection, marker_id))
                marker_id += 2
                continue

            if detection.object_type == "seat" and detection.role in ("source", "target"):
                markers.markers.extend(self.seat_markers(detection, marker_id))
                marker_id += 2
                continue

            if detection.object_type == "item" and detection.role == "source":
                markers.markers.extend(self.item_markers(detection, marker_id))
                marker_id += 2

        self.marker_pub.publish(markers)

    def chair_markers(self, detection, marker_id):
        if detection.id == self.source_chair:
            color = (0.0, 1.0, 0.0, 0.50)
            label = f"SOURCE {detection.id}"
        elif detection.id == self.target_chair:
            color = (0.0, 0.6, 1.0, 0.50)
            label = f"TARGET {detection.id}"
        else:
            color = (0.7, 0.7, 0.7, 0.35)
            label = detection.id
        return [
            self.cube_marker(
                detection,
                marker_id,
                scale=(self.chair_scale, self.chair_scale, self.chair_scale),
                color=color,
                ns="chairs",
            ),
            self.text_marker(detection, marker_id + 1, label, z_offset=self.chair_scale * 0.8),
        ]

    def seat_markers(self, detection, marker_id):
        label = f"{detection.role.upper()} SEAT"
        return [
            self.cube_marker(
                detection,
                marker_id,
                scale=(self.chair_scale, self.chair_scale, self.seat_height),
                color=(1.0, 1.0, 0.0, 0.65),
                ns="seats",
            ),
            self.text_marker(detection, marker_id + 1, label, z_offset=0.15),
        ]

    def item_markers(self, detection, marker_id):
        return [
            self.cube_marker(
                detection,
                marker_id,
                scale=(self.item_scale, self.item_scale, self.item_scale),
                color=(1.0, 0.0, 0.0, 0.90),
                ns="items",
            ),
            self.text_marker(detection, marker_id + 1, "ITEM", z_offset=0.10),
        ]

    def cube_marker(self, detection, marker_id, scale, color, ns):
        marker = self.base_marker(detection, marker_id, ns)
        marker.type = Marker.CUBE
        marker.scale.x = float(scale[0])
        marker.scale.y = float(scale[1])
        marker.scale.z = float(scale[2])
        marker.color.r = float(color[0])
        marker.color.g = float(color[1])
        marker.color.b = float(color[2])
        marker.color.a = float(color[3])
        return marker

    def text_marker(self, detection, marker_id, text, z_offset):
        marker = self.base_marker(detection, marker_id, "labels")
        marker.type = Marker.TEXT_VIEW_FACING
        marker.pose.position.z += float(z_offset)
        marker.scale.z = 0.15
        marker.color.r = 1.0
        marker.color.g = 1.0
        marker.color.b = 1.0
        marker.color.a = 1.0
        marker.text = text
        return marker

    def base_marker(self, detection, marker_id, ns):
        marker = Marker()
        marker.header = detection.header
        marker.ns = ns
        marker.id = int(marker_id)
        marker.action = Marker.ADD
        marker.pose.position.x = float(detection.x)
        marker.pose.position.y = float(detection.y)
        marker.pose.position.z = float(detection.z)
        marker.pose.orientation.w = 1.0
        marker.lifetime = rospy.Duration(self.marker_lifetime)
        return marker


def main():
    rospy.init_node("rviz_marker_publisher")
    RVizMarkerPublisher()
    rospy.loginfo("Colt RViz markers publishing on %s", rospy.get_param("~marker_topic", "/colt/ui/rviz_markers"))
    rospy.spin()


if __name__ == "__main__":
    main()
