#!/usr/bin/env python3
"""Simple wp_tilt scan and selected-chair tracking for Colt."""

import math

import rospy
from bridle_common import clamp, detection_by_id, joint_state_command
from colt_msgs.msg import Detection3D, Detection3DArray
from sensor_msgs.msg import CameraInfo, JointState
from std_msgs.msg import String, UInt8


PT_STATE_SOURCE = 0
PT_STATE_TARGET = 1


class PTControlNode:
    def __init__(self):
        self.image_width = int(rospy.get_param("~image_width", 960))
        self.image_height = int(rospy.get_param("~image_height", 540))
        self.command_topic = rospy.get_param("~command_topic", "/wpv4_pt/joint_ctrl_degree")
        self.joint_states_topic = rospy.get_param("~joint_states_topic", "/joint_states")
        self.camera_info_topic = rospy.get_param("~camera_info_topic", "/kinect2/qhd/camera_info")
        self.detections_topic = rospy.get_param("~detections_topic", "/colt/bridle/detections")
        self.source_topic = rospy.get_param("~source_topic", "/colt/ui/selected_source_chair")
        self.target_topic = rospy.get_param("~target_topic", "/colt/ui/selected_target_chair")
        self.pt_state_topic = rospy.get_param("~pt_state_topic", "/colt/ui/pt_state")

        self.command_rate_hz = float(rospy.get_param("~command_rate_hz", 5.0))
        self.detection_timeout_sec = float(rospy.get_param("~detection_timeout_sec", 2.0))
        self.tilt_track_gain_deg = float(rospy.get_param("~tilt_track_gain_deg", 4.0))
        self.pitch_track_gain_deg = float(rospy.get_param("~pitch_track_gain_deg", 1.0))
        self.max_tilt_step_deg = float(rospy.get_param("~max_tilt_step_deg", 2.0))
        self.max_pitch_step_deg = float(rospy.get_param("~max_pitch_step_deg", 0.4))
        self.track_pitch = bool(rospy.get_param("~track_pitch", True))
        self.center_deadband = float(rospy.get_param("~center_deadband", 0.04))
        self.scan_step_deg = float(rospy.get_param("~scan_step_deg", 1.0))
        self.scan_pitch_step_deg = float(rospy.get_param("~scan_pitch_step_deg", self.scan_step_deg))
        self.wp_tilt_min_deg = float(rospy.get_param("~wp_tilt_min_deg", -20.0))
        self.wp_tilt_max_deg = float(rospy.get_param("~wp_tilt_max_deg", 20.0))
        self.wp_pitch_min_deg = float(rospy.get_param("~wp_pitch_min_deg", 0.0))
        self.wp_pitch_max_deg = float(rospy.get_param("~wp_pitch_max_deg", 30.0))
        self.forward_pitch_deg = float(rospy.get_param("~forward_pitch_deg", 0.0))
        self.command_velocity = float(rospy.get_param("~command_velocity", 300.0))
        self.local_search_hold_sec = float(rospy.get_param("~local_search_hold_sec", 0.8))
        self.local_search_sec = float(rospy.get_param("~local_search_sec", 4.0))
        self.local_search_tilt_deg = float(rospy.get_param("~local_search_tilt_deg", 8.0))
        self.local_search_pitch_deg = float(rospy.get_param("~local_search_pitch_deg", 5.0))

        self.wp_tilt_deg = 0.0
        self.wp_pitch_deg = self.forward_pitch_deg
        self.command_tilt_deg = 0.0
        self.command_pitch_deg = self.forward_pitch_deg
        self.command_initialized = False
        self.has_joint_state = False
        self.scan_tilt_direction = 1.0
        self.scan_pitch_direction = 1.0
        self.pt_state = PT_STATE_SOURCE
        self.selection = {"source": "", "target": ""}
        self.detections = []
        self.target_stamp = rospy.Time(0)
        self.scan_reason = "waiting for detections"
        self.last_visible_role = ""
        self.last_visible_chair_id = ""
        self.last_visible_stamp = rospy.Time(0)
        self.last_visible_tilt_deg = 0.0
        self.last_visible_pitch_deg = self.forward_pitch_deg
        self.last_visible_bbox = None
        self.local_search_tilt_direction = 1.0
        self.local_search_pitch_direction = 1.0

        self.command_pub = rospy.Publisher(self.command_topic, JointState, queue_size=1)
        rospy.Subscriber(self.detections_topic, Detection3DArray, self.detections_cb, queue_size=1)
        rospy.Subscriber(self.joint_states_topic, JointState, self.joint_states_cb, queue_size=10)
        rospy.Subscriber(self.camera_info_topic, CameraInfo, self.camera_info_cb, queue_size=1)
        rospy.Subscriber(self.source_topic, String, self.selection_cb("source"), queue_size=1)
        rospy.Subscriber(self.target_topic, String, self.selection_cb("target"), queue_size=1)
        rospy.Subscriber(self.pt_state_topic, UInt8, self.pt_state_cb, queue_size=1)
        rospy.Timer(rospy.Duration(1.0 / self.command_rate_hz), self.control_tick)

    def camera_info_cb(self, msg):
        self.image_width = int(msg.width)
        self.image_height = int(msg.height)

    def joint_states_cb(self, msg):
        if len(msg.position) < 2:
            return
        if "wp_tilt" in msg.name and "wp_pitch" in msg.name:
            self.wp_tilt_deg = math.degrees(float(msg.position[msg.name.index("wp_tilt")]))
            self.wp_pitch_deg = math.degrees(float(msg.position[msg.name.index("wp_pitch")]))
        elif not msg.name:
            self.wp_tilt_deg = math.degrees(float(msg.position[0]))
            self.wp_pitch_deg = math.degrees(float(msg.position[1]))
        else:
            return
        if not self.command_initialized:
            self.command_tilt_deg = clamp(self.wp_tilt_deg, self.wp_tilt_min_deg, self.wp_tilt_max_deg)
            self.command_pitch_deg = clamp(self.wp_pitch_deg, self.wp_pitch_min_deg, self.wp_pitch_max_deg)
            self.command_initialized = True
        self.has_joint_state = True

    def detections_cb(self, msg):
        self.detections = list(msg.detections)
        self.target_stamp = rospy.Time.now()

    def selection_cb(self, role):
        def callback(msg):
            self.selection[role] = msg.data.strip()
            self.scan_reason = ""

        return callback

    def pt_state_cb(self, msg):
        self.pt_state = PT_STATE_TARGET if int(msg.data) == PT_STATE_TARGET else PT_STATE_SOURCE

    def control_tick(self, _event):
        if not self.has_joint_state:
            return
        next_tilt, next_pitch = self.next_angles()
        self.command_tilt_deg = float(next_tilt)
        self.command_pitch_deg = float(next_pitch)
        command = joint_state_command(
            names=["wp_tilt", "wp_pitch"],
            positions=[next_tilt, next_pitch],
            velocity=self.command_velocity,
            stamp=rospy.Time.now(),
        )
        self.command_pub.publish(command)

    def next_angles(self):
        role, chair_id = self.desired_target()
        target = self.active_target(role, chair_id)
        if target is None:
            recovery = self.recovery_angles(role, chair_id)
            rospy.logwarn_throttle(3.0, "PT scanning: %s", self.scan_reason)
            if recovery is not None:
                return recovery
            return self.scan_angles()
        next_tilt, next_pitch = self.track_angles(target)
        self.remember_visible_target(role, chair_id, target, next_tilt, next_pitch)
        return next_tilt, next_pitch

    def desired_target(self):
        role = "target" if self.pt_state == PT_STATE_TARGET else "source"
        return role, self.selection.get(role, "")

    def active_target(self, role, chair_id):
        if (rospy.Time.now() - self.target_stamp).to_sec() > self.detection_timeout_sec:
            age = (rospy.Time.now() - self.target_stamp).to_sec()
            self.scan_reason = f"detections stale age={age:.2f}s timeout={self.detection_timeout_sec:.2f}s"
            return None
        if not chair_id:
            self.scan_reason = f"{role} chair is not selected"
            return None
        detection = detection_by_id(self.detections, chair_id, object_type="chair")
        if detection is None:
            self.scan_reason = f"{role} {chair_id} is not in detections; {self.visible_chair_summary()}"
            return None
        if int(detection.state) == Detection3D.STATE_LOST:
            self.scan_reason = f"{role} {chair_id} is lost; {self.visible_chair_summary()}"
            return None
        self.scan_reason = ""
        return detection

    def remember_visible_target(self, role, chair_id, detection, next_tilt, next_pitch):
        self.last_visible_role = role
        self.last_visible_chair_id = chair_id
        self.last_visible_stamp = rospy.Time.now()
        self.last_visible_tilt_deg = float(next_tilt)
        self.last_visible_pitch_deg = float(next_pitch)
        self.last_visible_bbox = (
            int(detection.bbox.xmin),
            int(detection.bbox.ymin),
            int(detection.bbox.xmax),
            int(detection.bbox.ymax),
        )
        self.local_search_tilt_direction = 1.0
        self.local_search_pitch_direction = 1.0

    def recovery_angles(self, role, chair_id):
        if not chair_id or role != self.last_visible_role or chair_id != self.last_visible_chair_id:
            return None
        if self.last_visible_stamp == rospy.Time(0):
            return None

        elapsed = (rospy.Time.now() - self.last_visible_stamp).to_sec()
        if elapsed <= self.local_search_hold_sec:
            self.scan_reason = f"{role} {chair_id} lost, holding last angle for {elapsed:.2f}s"
            return self.last_visible_tilt_deg, self.last_visible_pitch_deg

        local_elapsed = elapsed - self.local_search_hold_sec
        if local_elapsed <= self.local_search_sec:
            self.scan_reason = f"{role} {chair_id} lost, local search {local_elapsed:.2f}s/{self.local_search_sec:.2f}s"
            return self.local_search_angles()
        return None

    def visible_chair_summary(self):
        visible = [
            f"{item.id}:{item.role or 'normal'}:state={int(item.state)}"
            for item in self.detections
            if item.object_type == "chair" and int(item.state) != Detection3D.STATE_LOST
        ]
        return "visible_chairs=" + (",".join(visible) if visible else "<none>")

    def scan_angles(self):
        next_tilt, self.scan_tilt_direction = self.scan_axis(
            self.command_tilt_deg,
            self.wp_tilt_min_deg,
            self.wp_tilt_max_deg,
            self.scan_step_deg,
            self.scan_tilt_direction,
        )
        next_pitch = clamp(self.forward_pitch_deg, self.wp_pitch_min_deg, self.wp_pitch_max_deg)
        return next_tilt, next_pitch

    def scan_axis(self, current, low, high, step, direction):
        if high <= low:
            return float(low), direction
        next_value = float(current) + float(direction) * abs(float(step))
        if next_value >= high:
            return float(high), -1.0
        if next_value <= low:
            return float(low), 1.0
        return next_value, direction

    def local_search_angles(self):
        tilt_low = max(self.wp_tilt_min_deg, self.last_visible_tilt_deg - self.local_search_tilt_deg)
        tilt_high = min(self.wp_tilt_max_deg, self.last_visible_tilt_deg + self.local_search_tilt_deg)
        pitch_low = max(self.wp_pitch_min_deg, self.last_visible_pitch_deg - self.local_search_pitch_deg)
        pitch_high = min(self.wp_pitch_max_deg, self.last_visible_pitch_deg + self.local_search_pitch_deg)
        next_tilt, self.local_search_tilt_direction = self.scan_axis(
            self.command_tilt_deg,
            tilt_low,
            tilt_high,
            self.scan_step_deg,
            self.local_search_tilt_direction,
        )
        next_pitch, self.local_search_pitch_direction = self.scan_axis(
            self.command_pitch_deg,
            pitch_low,
            pitch_high,
            self.scan_pitch_step_deg,
            self.local_search_pitch_direction,
        )
        return next_tilt, next_pitch

    def track_angles(self, detection):
        bbox = detection.bbox
        center_x = 0.5 * (float(bbox.xmin) + float(bbox.xmax))
        center_y = 0.5 * (float(bbox.ymin) + float(bbox.ymax))
        error_x = (center_x - self.image_width * 0.5) / max(self.image_width * 0.5, 1.0)
        error_y = (center_y - self.image_height * 0.5) / max(self.image_height * 0.5, 1.0)

        tilt_delta = self.step_from_error(error_x, self.tilt_track_gain_deg, self.max_tilt_step_deg)
        next_tilt = clamp(self.command_tilt_deg - tilt_delta, self.wp_tilt_min_deg, self.wp_tilt_max_deg)
        if self.track_pitch:
            pitch_delta = self.step_from_error(error_y, self.pitch_track_gain_deg, self.max_pitch_step_deg)
            next_pitch = clamp(self.command_pitch_deg - pitch_delta, self.wp_pitch_min_deg, self.wp_pitch_max_deg)
        else:
            next_pitch = clamp(self.command_pitch_deg, self.wp_pitch_min_deg, self.wp_pitch_max_deg)
        return next_tilt, next_pitch

    def step_from_error(self, error, gain, max_step):
        if abs(error) < self.center_deadband:
            return 0.0
        return clamp(error * gain, -max_step, max_step)


def main():
    rospy.init_node("colt_pt_control")
    PTControlNode()
    rospy.loginfo(
        "Colt pan-tilt control publishing %s with pt_state topic %s",
        rospy.get_param("~command_topic", "/wpv4_pt/joint_ctrl_degree"),
        rospy.get_param("~pt_state_topic", "/colt/ui/pt_state"),
    )
    rospy.spin()


if __name__ == "__main__":
    main()
