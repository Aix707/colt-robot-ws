#!/usr/bin/env python3
"""Publish configurable fake Colt perception candidates for pipeline smoke tests."""

import math

import rospy
from colt_msgs.msg import Box2D, Box3D, Detection3D, Detection3DArray
from geometry_msgs.msg import Point, PoseStamped, Quaternion, Vector3
from std_msgs.msg import Header


def make_pose(header, center):
    pose = PoseStamped()
    pose.header = header
    pose.pose.position = Point(x=center[0], y=center[1], z=center[2])
    pose.pose.orientation = Quaternion(x=0.0, y=0.0, z=0.0, w=1.0)
    return pose


def make_detection(header, spec):
    detection = Detection3D()
    detection.header = header
    detection.id = spec["id"]
    detection.class_name = spec["class_name"]
    detection.role = spec.get("role", "candidate")
    detection.state = spec.get("state", "candidate")
    detection.confidence = float(spec.get("confidence", 0.8))
    detection.bbox = Box2D(
        xmin=int(spec["bbox"][0]),
        ymin=int(spec["bbox"][1]),
        xmax=int(spec["bbox"][2]),
        ymax=int(spec["bbox"][3]),
        confidence=detection.confidence,
        class_name=detection.class_name,
    )
    detection.box = Box3D(
        center=Point(x=spec["center"][0], y=spec["center"][1], z=spec["center"][2]),
        size=Vector3(x=spec["size"][0], y=spec["size"][1], z=spec["size"][2]),
        orientation=Quaternion(x=0.0, y=0.0, z=0.0, w=1.0),
        confidence=detection.confidence,
        class_name=detection.class_name,
    )
    detection.pose = make_pose(header, spec["center"])
    detection.coordinate_method = spec.get("coordinate_method", "fake_candidate")
    detection.depth_valid = bool(spec.get("depth_valid", True))
    detection.geometry_constraint_passed = bool(spec.get("geometry_constraint_passed", True))
    detection.history_constraint_passed = bool(spec.get("history_constraint_passed", True))
    return detection


def chair_specs(chair_count):
    base_specs = [
        {
            "chair_id": "chair_0",
            "chair_center": (1.05, 0.32, 0.43),
            "seat_center": (1.05, 0.32, 0.50),
            "bbox": (190, 145, 515, 430),
        },
        {
            "chair_id": "chair_1",
            "chair_center": (1.22, -0.34, 0.44),
            "seat_center": (1.22, -0.34, 0.51),
            "bbox": (540, 150, 850, 430),
        },
        {
            "chair_id": "chair_2",
            "chair_center": (1.55, 0.08, 0.45),
            "seat_center": (1.55, 0.08, 0.52),
            "bbox": (875, 165, 1140, 430),
        },
    ]
    return base_specs[: max(1, min(int(chair_count), len(base_specs)))]


def scene_specs(t):
    chair_count = rospy.get_param("~chair_count", 2)
    aluminum_chair = rospy.get_param("~aluminum_chair", "chair_0")
    aluminum_outside_seat = bool(rospy.get_param("~aluminum_outside_seat", False))
    aluminum_bob_m = float(rospy.get_param("~aluminum_bob_m", 0.004))

    specs = []
    seats = {}
    for item in chair_specs(chair_count):
        chair_id = item["chair_id"]
        seat_id = f"{chair_id}_seat"
        seats[chair_id] = item["seat_center"]
        specs.append(
            {
                "id": chair_id,
                "class_name": "chair",
                "role": "candidate_chair",
                "state": "candidate",
                "confidence": 0.90,
                "bbox": item["bbox"],
                "center": item["chair_center"],
                "size": (0.56, 0.52, 0.86),
                "coordinate_method": "fake_chair_center",
            }
        )
        specs.append(
            {
                "id": seat_id,
                "class_name": "chair_seat",
                "role": "candidate_seat",
                "state": "candidate",
                "confidence": 0.92,
                "bbox": (
                    item["bbox"][0] + 30,
                    item["bbox"][1] + 75,
                    item["bbox"][2] - 30,
                    item["bbox"][3] - 35,
                ),
                "center": item["seat_center"],
                "size": (0.46, 0.42, 0.035),
                "coordinate_method": "fake_seat_plane",
            }
        )

    seat_center = seats.get(aluminum_chair, next(iter(seats.values())))
    y_offset = 0.70 if aluminum_outside_seat else -0.08
    aluminum_center = (
        seat_center[0] - 0.10,
        seat_center[1] + y_offset,
        seat_center[2] + 0.03 + aluminum_bob_m * math.sin(t),
    )
    specs.append(
        {
            "id": "aluminum_block_0",
            "class_name": "aluminum_block",
            "role": "candidate_aluminum",
            "state": "candidate",
            "confidence": 0.84,
            "bbox": (320, 250, 382, 310),
            "center": aluminum_center,
            "size": (0.05, 0.05, 0.05),
            "coordinate_method": "fake_aluminum_center",
        }
    )
    return specs


def main():
    rospy.init_node("colt_fake_candidate_publisher")
    frame_id = rospy.get_param("~frame_id", "base_footprint")
    rate_hz = float(rospy.get_param("~rate", 2.0))
    pub = rospy.Publisher("/colt/bridle/candidates", Detection3DArray, queue_size=10)
    rospy.loginfo("Publishing fake candidates on /colt/bridle/candidates")

    start = rospy.Time.now()
    rate = rospy.Rate(rate_hz)
    while not rospy.is_shutdown():
        now = rospy.Time.now()
        header = Header(stamp=now, frame_id=frame_id)
        elapsed = (now - start).to_sec()
        array = Detection3DArray()
        array.header = header
        array.detections = [make_detection(header, spec) for spec in scene_specs(elapsed)]
        array.scene_state = "fake_candidates"
        pub.publish(array)
        rate.sleep()


if __name__ == "__main__":
    main()
