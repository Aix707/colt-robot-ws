#!/usr/bin/env python3
"""Fuse candidate detections with UI chair selections into stable Colt scene outputs."""

import copy
import json
from math import fabs

import rospy
from colt_msgs.msg import Detection3D, Detection3DArray, PerceptionState
from geometry_msgs.msg import Point, PoseStamped, Quaternion
from std_msgs.msg import Header, String


def point_tuple(point):
    return (float(point.x), float(point.y), float(point.z))


def set_detection_role_state(detection, role, state, geometry_ok=True):
    item = copy.deepcopy(detection)
    item.role = role
    item.state = state
    item.geometry_constraint_passed = bool(geometry_ok)
    item.history_constraint_passed = True
    return item


def make_pose(header, point, z_offset=0.0):
    pose = PoseStamped()
    pose.header = header
    pose.pose.position = Point(x=point.x, y=point.y, z=point.z + z_offset)
    pose.pose.orientation = Quaternion(x=0.0, y=0.0, z=0.0, w=1.0)
    return pose


def empty_state(header, state, detail):
    msg = PerceptionState()
    msg.header = header
    msg.state = state
    msg.active_task = "scene_fusion"
    msg.detail = json.dumps(detail, ensure_ascii=True, sort_keys=True)
    msg.ready_for_navigation = False
    msg.ready_for_grasp = False
    msg.ready_for_place = False
    return msg


class SceneFusionNode:
    def __init__(self):
        self.selected_source = rospy.get_param("~default_source_chair", "")
        self.selected_target = rospy.get_param("~default_target_chair", "")
        self.max_aluminum_height_m = float(rospy.get_param("~max_aluminum_height_m", 0.08))
        self.seat_margin_m = float(rospy.get_param("~seat_margin_m", 0.02))
        self.aluminum_height_m = float(rospy.get_param("~aluminum_height_m", 0.05))
        self.last_candidates = None

        self.detections_pub = rospy.Publisher(
            "/colt/bridle/detections", Detection3DArray, queue_size=10
        )
        self.source_seat_pub = rospy.Publisher(
            "/colt/bridle/source_seat_pose", PoseStamped, queue_size=10
        )
        self.target_seat_pub = rospy.Publisher(
            "/colt/bridle/target_seat_pose", PoseStamped, queue_size=10
        )
        self.aluminum_pub = rospy.Publisher(
            "/colt/bridle/aluminum_target", PoseStamped, queue_size=10
        )
        self.grasp_pub = rospy.Publisher("/colt/bridle/grasp_pose", PoseStamped, queue_size=10)
        self.place_pub = rospy.Publisher("/colt/bridle/place_pose", PoseStamped, queue_size=10)
        self.state_pub = rospy.Publisher(
            "/colt/bridle/perception_state", PerceptionState, queue_size=10
        )

        rospy.Subscriber("/colt/bridle/candidates", Detection3DArray, self.candidates_cb)
        rospy.Subscriber("/colt/ui/selected_source_chair", String, self.source_cb)
        rospy.Subscriber("/colt/ui/selected_target_chair", String, self.target_cb)

    def source_cb(self, msg):
        self.selected_source = msg.data.strip()
        self.publish_scene()

    def target_cb(self, msg):
        self.selected_target = msg.data.strip()
        self.publish_scene()

    def candidates_cb(self, msg):
        self.last_candidates = msg
        self.publish_scene()

    def indexes(self):
        chairs = {}
        seats = {}
        aluminums = []
        if self.last_candidates is None:
            return chairs, seats, aluminums
        for detection in self.last_candidates.detections:
            if detection.class_name == "chair":
                chairs[detection.id] = detection
            elif detection.class_name == "chair_seat":
                seats[detection.id] = detection
            elif detection.class_name == "aluminum_block":
                aluminums.append(detection)
        return chairs, seats, aluminums

    def seat_for_chair(self, chair_id, seats, chairs):
        expected = f"{chair_id}_seat"
        if expected in seats:
            return seats[expected]
        chair = chairs.get(chair_id)
        if chair is None or not seats:
            return None
        cx, cy, _ = point_tuple(chair.pose.pose.position)
        return min(
            seats.values(),
            key=lambda seat: (seat.pose.pose.position.x - cx) ** 2
            + (seat.pose.pose.position.y - cy) ** 2,
        )

    def inside_seat(self, point, seat):
        px, py, pz = point_tuple(point)
        sx, sy, sz = point_tuple(seat.pose.pose.position)
        half_x = max(float(seat.box.size.x) * 0.5 - self.seat_margin_m, 0.0)
        half_y = max(float(seat.box.size.y) * 0.5 - self.seat_margin_m, 0.0)
        height = pz - sz
        return (
            fabs(px - sx) <= half_x
            and fabs(py - sy) <= half_y
            and 0.0 <= height <= self.max_aluminum_height_m
        )

    def best_aluminum(self, aluminums, source_seat):
        if source_seat is None:
            return None, False
        if not aluminums:
            return None, False
        best = max(aluminums, key=lambda item: item.confidence)
        return best, self.inside_seat(best.pose.pose.position, source_seat)

    def scene_detail(self, errors, source_seat, target_seat, aluminum, aluminum_ok):
        return {
            "selected_source_chair": self.selected_source,
            "selected_target_chair": self.selected_target,
            "source_seat": source_seat.id if source_seat else "",
            "target_seat": target_seat.id if target_seat else "",
            "aluminum": aluminum.id if aluminum else "",
            "aluminum_on_source_seat": bool(aluminum_ok),
            "errors": errors,
        }

    def publish_scene(self):
        if self.last_candidates is None:
            return

        header = Header(
            stamp=rospy.Time.now(),
            frame_id=self.last_candidates.header.frame_id or "base_footprint",
        )
        chairs, seats, aluminums = self.indexes()
        errors = []
        output = []

        source_chair = chairs.get(self.selected_source)
        target_chair = chairs.get(self.selected_target)
        if not self.selected_source:
            errors.append("source_chair_not_selected")
        elif source_chair is None:
            errors.append("source_chair_not_found")
        if not self.selected_target:
            errors.append("target_chair_not_selected")
        elif target_chair is None:
            errors.append("target_chair_not_found")

        source_seat = self.seat_for_chair(self.selected_source, seats, chairs)
        target_seat = self.seat_for_chair(self.selected_target, seats, chairs)
        if self.selected_source and source_seat is None:
            errors.append("source_seat_not_found")
        if self.selected_target and target_seat is None:
            errors.append("target_seat_not_found")

        aluminum, aluminum_ok = self.best_aluminum(aluminums, source_seat)
        if source_seat is not None and aluminum is None:
            errors.append("aluminum_not_found")
        elif source_seat is not None and not aluminum_ok:
            errors.append("aluminum_outside_source_seat")

        for chair_id, chair in chairs.items():
            if chair_id == self.selected_source and source_chair is not None:
                output.append(set_detection_role_state(chair, "source_chair", "stable"))
            elif chair_id == self.selected_target and target_chair is not None:
                output.append(set_detection_role_state(chair, "target_chair", "stable"))
            else:
                output.append(set_detection_role_state(chair, "candidate_chair", "candidate"))
        for seat in seats.values():
            if source_seat is not None and seat.id == source_seat.id:
                state = "ready_for_grasp" if aluminum_ok else "stable"
                output.append(set_detection_role_state(seat, "source_seat", state))
            elif target_seat is not None and seat.id == target_seat.id:
                output.append(set_detection_role_state(seat, "target_seat", "ready_for_place"))
            else:
                output.append(set_detection_role_state(seat, "candidate_seat", "candidate"))
        for item in aluminums:
            if aluminum is not None and item.id == aluminum.id:
                state = "stable" if aluminum_ok else "candidate"
                output.append(
                    set_detection_role_state(item, "aluminum_block", state, geometry_ok=aluminum_ok)
                )
            else:
                output.append(set_detection_role_state(item, "candidate_aluminum", "candidate"))

        ready_for_grasp = source_seat is not None and aluminum is not None and aluminum_ok
        ready_for_place = target_seat is not None
        state = "ready" if ready_for_grasp and ready_for_place else "not_ready"
        if not errors and ready_for_grasp and not ready_for_place:
            state = "ready_for_grasp"
        elif not errors and ready_for_place and not ready_for_grasp:
            state = "ready_for_place"

        array = Detection3DArray()
        array.header = header
        array.detections = output
        array.scene_state = state
        self.detections_pub.publish(array)

        if source_seat is not None:
            self.source_seat_pub.publish(make_pose(header, source_seat.pose.pose.position))
        if target_seat is not None:
            target_pose = make_pose(header, target_seat.pose.pose.position)
            self.target_seat_pub.publish(target_pose)
            place_pose = make_pose(
                header,
                target_seat.pose.pose.position,
                z_offset=self.aluminum_height_m * 0.5,
            )
            self.place_pub.publish(place_pose)
        if ready_for_grasp:
            aluminum_pose = make_pose(header, aluminum.pose.pose.position)
            self.aluminum_pub.publish(aluminum_pose)
            self.grasp_pub.publish(aluminum_pose)

        detail = self.scene_detail(errors, source_seat, target_seat, aluminum, aluminum_ok)
        msg = empty_state(header, state, detail)
        msg.ready_for_grasp = ready_for_grasp
        msg.ready_for_place = ready_for_place
        msg.ready_for_navigation = source_seat is not None or target_seat is not None
        self.state_pub.publish(msg)


def main():
    rospy.init_node("colt_scene_fusion")
    SceneFusionNode()
    rospy.loginfo("Colt scene fusion node ready")
    rospy.spin()


if __name__ == "__main__":
    main()
