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
        self.detection_timeout_sec = float(rospy.get_param("~detection_timeout_sec", 0.6))
        self.tilt_track_gain_deg = float(rospy.get_param("~tilt_track_gain_deg", 4.0))
        self.pitch_track_gain_deg = float(rospy.get_param("~pitch_track_gain_deg", 1.0))
        self.max_tilt_step_deg = float(rospy.get_param("~max_tilt_step_deg", 2.0))
        self.max_pitch_step_deg = float(rospy.get_param("~max_pitch_step_deg", 0.4))
        self.track_pitch = bool(rospy.get_param("~track_pitch", False))
        self.center_deadband = float(rospy.get_param("~center_deadband", 0.04))
        self.scan_step_deg = float(rospy.get_param("~scan_step_deg", 1.0))
        self.wp_tilt_min_deg = float(rospy.get_param("~wp_tilt_min_deg", -20.0))
        self.wp_tilt_max_deg = float(rospy.get_param("~wp_tilt_max_deg", 20.0))
        self.wp_pitch_min_deg = float(rospy.get_param("~wp_pitch_min_deg", -20.0))
        self.wp_pitch_max_deg = float(rospy.get_param("~wp_pitch_max_deg", 0.0))
        self.forward_pitch_deg = float(rospy.get_param("~forward_pitch_deg", 0.0))
        self.command_velocity = float(rospy.get_param("~command_velocity", 300.0))

        self.wp_tilt_deg = 0.0
        self.wp_pitch_deg = self.forward_pitch_deg
        self.has_joint_state = False
        self.scan_direction = 1.0
        self.pt_state = PT_STATE_SOURCE
        self.selection = {"source": "", "target": ""}
        self.detections = []
        self.target_stamp = rospy.Time(0)

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
        else:
            self.wp_tilt_deg = math.degrees(float(msg.position[0]))
            self.wp_pitch_deg = math.degrees(float(msg.position[1]))
        self.has_joint_state = True

    def detections_cb(self, msg):
        self.detections = list(msg.detections)
        self.target_stamp = msg.header.stamp if msg.header.stamp != rospy.Time(0) else rospy.Time.now()

    def selection_cb(self, role):
        def callback(msg):
            self.selection[role] = msg.data.strip()

        return callback

    def pt_state_cb(self, msg):
        self.pt_state = PT_STATE_TARGET if int(msg.data) == PT_STATE_TARGET else PT_STATE_SOURCE

    def control_tick(self, _event):
        if not self.has_joint_state:
            return
        next_tilt, next_pitch = self.next_angles()
        command = joint_state_command(
            names=["wp_tilt", "wp_pitch"],
            positions=[next_tilt, next_pitch],
            velocity=self.command_velocity,
            stamp=rospy.Time.now(),
        )
        self.command_pub.publish(command)

    def next_angles(self):
        target = self.active_target()
        if target is None:
            return self.scan_angles()
        return self.track_angles(target)

    def active_target(self):
        if (rospy.Time.now() - self.target_stamp).to_sec() > self.detection_timeout_sec:
            return None
        if not self.selection.get("source") or not self.selection.get("target"):
            return None
        role = "target" if self.pt_state == PT_STATE_TARGET else "source"
        chair_id = self.selection.get(role, "")
        detection = detection_by_id(self.detections, chair_id, object_type="chair")
        if detection is None or int(detection.state) == Detection3D.STATE_LOST:
            return None
        return detection

    def scan_angles(self):
        next_tilt = self.wp_tilt_deg + self.scan_direction * self.scan_step_deg
        if next_tilt >= self.wp_tilt_max_deg:
            next_tilt = self.wp_tilt_max_deg
            self.scan_direction = -1.0
        elif next_tilt <= self.wp_tilt_min_deg:
            next_tilt = self.wp_tilt_min_deg
            self.scan_direction = 1.0
        next_pitch = clamp(self.forward_pitch_deg, self.wp_pitch_min_deg, self.wp_pitch_max_deg)
        return next_tilt, next_pitch

    def track_angles(self, detection):
        bbox = detection.bbox
        center_x = 0.5 * (float(bbox.xmin) + float(bbox.xmax))
        center_y = 0.5 * (float(bbox.ymin) + float(bbox.ymax))
        error_x = (center_x - self.image_width * 0.5) / max(self.image_width * 0.5, 1.0)
        error_y = (center_y - self.image_height * 0.5) / max(self.image_height * 0.5, 1.0)

        tilt_delta = self.step_from_error(error_x, self.tilt_track_gain_deg, self.max_tilt_step_deg)
        next_tilt = clamp(self.wp_tilt_deg + tilt_delta, self.wp_tilt_min_deg, self.wp_tilt_max_deg)
        if self.track_pitch:
            pitch_delta = self.step_from_error(error_y, self.pitch_track_gain_deg, self.max_pitch_step_deg)
            next_pitch = clamp(self.wp_pitch_deg - pitch_delta, self.wp_pitch_min_deg, self.wp_pitch_max_deg)
        else:
            next_pitch = clamp(self.forward_pitch_deg, self.wp_pitch_min_deg, self.wp_pitch_max_deg)
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
