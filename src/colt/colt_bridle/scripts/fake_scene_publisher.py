#!/usr/bin/env python3
"""Publish a static Colt perception scene for message and RViz smoke tests."""

import math

import rospy
from colt_msgs.msg import Box2D, Box3D, Detection3D, Detection3DArray
from geometry_msgs.msg import Point, PoseStamped, Quaternion, Vector3
from std_msgs.msg import ColorRGBA, Header
from visualization_msgs.msg import Marker, MarkerArray


def make_pose(header, x, y, z):
    pose = PoseStamped()
    pose.header = header
    pose.pose.position = Point(x=x, y=y, z=z)
    pose.pose.orientation = Quaternion(x=0.0, y=0.0, z=0.0, w=1.0)
    return pose


def make_detection(header, spec):
    detection = Detection3D()
    detection.header = header
    detection.id = spec["id"]
    detection.class_name = spec["class_name"]
    detection.role = spec["role"]
    detection.state = spec["state"]
    detection.confidence = spec["confidence"]
    detection.bbox = Box2D(
        xmin=spec["bbox"][0],
        ymin=spec["bbox"][1],
        xmax=spec["bbox"][2],
        ymax=spec["bbox"][3],
        confidence=spec["confidence"],
        class_name=spec["class_name"],
    )
    detection.box = Box3D(
        center=Point(x=spec["center"][0], y=spec["center"][1], z=spec["center"][2]),
        size=Vector3(x=spec["size"][0], y=spec["size"][1], z=spec["size"][2]),
        orientation=Quaternion(x=0.0, y=0.0, z=0.0, w=1.0),
        confidence=spec["confidence"],
        class_name=spec["class_name"],
    )
    detection.pose = make_pose(header, *spec["center"])
    detection.coordinate_method = spec["coordinate_method"]
    detection.depth_valid = True
    detection.geometry_constraint_passed = True
    detection.history_constraint_passed = True
    return detection


def color_for_detection(detection):
    if detection.state in ("stale", "occluded"):
        return ColorRGBA(0.5, 0.5, 0.5, 0.8)
    if detection.role == "source_seat":
        return ColorRGBA(0.0, 0.8, 0.2, 0.8)
    if detection.role == "target_seat":
        return ColorRGBA(0.0, 0.8, 1.0, 0.8)
    if detection.class_name == "aluminum_block" and detection.state == "stable":
        return ColorRGBA(1.0, 0.0, 0.0, 0.9)
    if detection.class_name == "aluminum_block":
        return ColorRGBA(1.0, 0.8, 0.0, 0.9)
    return ColorRGBA(0.8, 0.8, 0.8, 0.8)


def make_marker(header, detection, marker_id, marker_type, ns, scale, color, point=None):
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
    if point is not None:
        marker.pose.position = Point(x=point.x, y=point.y, z=point.z)
    marker.scale = scale
    marker.color = color
    marker.lifetime = rospy.Duration(0.75)
    return marker


def make_text_marker(header, detection, marker_id):
    marker = make_marker(
        header,
        detection,
        marker_id,
        Marker.TEXT_VIEW_FACING,
        "labels",
        Vector3(x=0.0, y=0.0, z=0.08),
        ColorRGBA(1.0, 1.0, 1.0, 0.95),
    )
    marker.pose.position.z += 0.12
    marker.text = (
        f"{detection.id} {detection.class_name} {detection.state}\n"
        f"p={detection.confidence:.2f}\n"
        f"x={detection.pose.pose.position.x:.2f} "
        f"y={detection.pose.pose.position.y:.2f} "
        f"z={detection.pose.pose.position.z:.2f}"
    )
    return marker


def make_markers(header, detections):
    markers = MarkerArray()
    marker_id = 0
    for detection in detections:
        color = color_for_detection(detection)
        center_scale = Vector3(x=0.05, y=0.05, z=0.05)
        if detection.class_name == "aluminum_block":
            center_scale = Vector3(x=0.035, y=0.035, z=0.035)

        markers.markers.append(
            make_marker(
                header,
                detection,
                marker_id,
                Marker.SPHERE,
                "center_points",
                center_scale,
                color,
            )
        )
        marker_id += 1

        box_color = ColorRGBA(color.r, color.g, color.b, 0.25)
        markers.markers.append(
            make_marker(
                header,
                detection,
                marker_id,
                Marker.CUBE,
                "boxes_3d",
                detection.box.size,
                box_color,
            )
        )
        marker_id += 1

        markers.markers.append(make_text_marker(header, detection, marker_id))
        marker_id += 1

    return markers


def scene_specs(t):
    bob = 0.01 * math.sin(t)
    return [
        {
            "id": "source_seat_0",
            "class_name": "chair_seat",
            "role": "source_seat",
            "state": "ready_for_grasp",
            "confidence": 0.92,
            "bbox": (210, 170, 510, 420),
            "center": (1.05, 0.32, 0.48),
            "size": (0.46, 0.42, 0.035),
            "coordinate_method": "seat_plane_fit",
        },
        {
            "id": "target_seat_0",
            "class_name": "chair_seat",
            "role": "target_seat",
            "state": "ready_for_place",
            "confidence": 0.89,
            "bbox": (560, 180, 840, 430),
            "center": (1.18, -0.34, 0.49),
            "size": (0.46, 0.42, 0.035),
            "coordinate_method": "seat_plane_fit",
        },
        {
            "id": "aluminum_block_0",
            "class_name": "aluminum_block",
            "role": "aluminum_block",
            "state": "stable",
            "confidence": 0.86,
            "bbox": (330, 245, 380, 300),
            "center": (0.94, 0.24, 0.535 + bob),
            "size": (0.05, 0.05, 0.05),
            "coordinate_method": "ray_seat_plane_intersection",
        },
    ]


def main():
    rospy.init_node("colt_fake_scene_publisher")
    frame_id = rospy.get_param("~frame_id", "base_footprint")
    rate_hz = rospy.get_param("~rate", 2.0)

    detection_pub = rospy.Publisher(
        "/colt/bridle/detections", Detection3DArray, queue_size=10
    )
    marker_pub = rospy.Publisher("/colt/bridle/markers", MarkerArray, queue_size=10)
    source_seat_pub = rospy.Publisher(
        "/colt/bridle/source_seat_pose", PoseStamped, queue_size=10
    )
    target_seat_pub = rospy.Publisher(
        "/colt/bridle/target_seat_pose", PoseStamped, queue_size=10
    )
    aluminum_pub = rospy.Publisher(
        "/colt/bridle/aluminum_target", PoseStamped, queue_size=10
    )

    rospy.loginfo(
        "Publishing fake Colt scene on /colt/bridle/detections and /colt/bridle/markers"
    )
    rate = rospy.Rate(rate_hz)
    start = rospy.Time.now()

    while not rospy.is_shutdown():
        now = rospy.Time.now()
        header = Header(stamp=now, frame_id=frame_id)
        t = (now - start).to_sec()
        detections = [make_detection(header, spec) for spec in scene_specs(t)]

        array = Detection3DArray()
        array.header = header
        array.detections = detections
        array.scene_state = "fake_ready"

        detection_pub.publish(array)
        marker_pub.publish(make_markers(header, detections))
        source_seat_pub.publish(detections[0].pose)
        target_seat_pub.publish(detections[1].pose)
        aluminum_pub.publish(detections[2].pose)

        rate.sleep()


if __name__ == "__main__":
    main()
