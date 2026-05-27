#!/usr/bin/env python3
"""Simple pan-tilt scan and chair-facing control for Colt."""

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
        self.raw_joint_states_topic = rospy.get_param("~raw_joint_states_topic", "/wpv4_pt/raw_joint_states")
        self.camera_info_topic = rospy.get_param("~camera_info_topic", "/kinect2/qhd/camera_info")
        self.detections_topic = rospy.get_param("~detections_topic", "/colt/bridle/detections")
        self.source_topic = rospy.get_param("~source_topic", "/colt/ui/selected_source_chair")
        self.target_topic = rospy.get_param("~target_topic", "/colt/ui/selected_target_chair")
        self.pt_state_topic = rospy.get_param("~pt_state_topic", "/colt/ui/pt_state")

        self.command_rate_hz = float(rospy.get_param("~command_rate_hz", 5.0))
        self.detection_timeout_sec = float(rospy.get_param("~detection_timeout_sec", 0.6))
        self.track_gain_deg = float(rospy.get_param("~track_gain_deg", 4.0))
        self.max_track_step_deg = float(rospy.get_param("~max_track_step_deg", 2.0))
        self.scan_step_deg = float(rospy.get_param("~scan_step_deg", 1.0))
        self.center_deadband = float(rospy.get_param("~center_deadband", 0.04))
        self.pan_min_deg = float(rospy.get_param("~pan_min_deg", -20.0))
        self.pan_max_deg = float(rospy.get_param("~pan_max_deg", 20.0))
        self.tilt_min_deg = float(rospy.get_param("~tilt_min_deg", -20.0))
        self.tilt_max_deg = float(rospy.get_param("~tilt_max_deg", 0.0))
        self.scan_tilt_deg = float(rospy.get_param("~scan_tilt_deg", 0.0))
        self.command_velocity = float(rospy.get_param("~command_velocity", 300.0))

        self.pan_deg = 0.0
        self.tilt_deg = 0.0
        self.has_joint_state = False
        self.scan_direction = 1.0
        self.pt_state = PT_STATE_SOURCE
        self.selection = {"source": "", "target": ""}
        self.detections = []
        self.target_stamp = rospy.Time(0)

        self.command_pub = rospy.Publisher(self.command_topic, JointState, queue_size=1)
        rospy.Subscriber(self.detections_topic, Detection3DArray, self.detections_cb, queue_size=1)
        rospy.Subscriber(self.raw_joint_states_topic, JointState, self.raw_joint_states_cb, queue_size=10)
        rospy.Subscriber(self.camera_info_topic, CameraInfo, self.camera_info_cb, queue_size=1)
        rospy.Subscriber(self.source_topic, String, self.selection_cb("source"), queue_size=1)
        rospy.Subscriber(self.target_topic, String, self.selection_cb("target"), queue_size=1)
        rospy.Subscriber(self.pt_state_topic, UInt8, self.pt_state_cb, queue_size=1)
        rospy.Timer(rospy.Duration(1.0 / self.command_rate_hz), self.control_tick)

    def camera_info_cb(self, msg):
        self.image_width = int(msg.width)
        self.image_height = int(msg.height)

    def raw_joint_states_cb(self, msg):
        if len(msg.position) < 2:
            return
        self.pan_deg = math.degrees(float(msg.position[0]))
        self.tilt_deg = math.degrees(float(msg.position[1]))
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
        next_pan, next_tilt = self.next_angles()
        command = joint_state_command(
            names=["wp_tilt", "wp_pitch"],
            positions=[next_pan, next_tilt],
            velocity=self.command_velocity,
            stamp=rospy.Time.now(),
        )
        self.command_pub.publish(command)

    def next_angles(self):
        target = self.active_target()
        if target is None:
            return self.scan_angles()
        return self.track_angles(target)

    def selection_ready(self):
        return bool(self.selection.get("source", "")) and bool(self.selection.get("target", ""))

    def active_target(self):
        if (rospy.Time.now() - self.target_stamp).to_sec() > self.detection_timeout_sec:
            return None
        if not self.selection_ready():
            return None
        role = "target" if self.pt_state == PT_STATE_TARGET else "source"
        chair_id = self.selection.get(role, "")
        if not chair_id:
            return None
        detection = detection_by_id(self.detections, chair_id, object_type="chair")
        if detection is None or int(detection.state) == Detection3D.STATE_LOST:
            return None
        return detection

    def scan_angles(self):
        next_pan = self.pan_deg + self.scan_direction * self.scan_step_deg
        if next_pan >= self.pan_max_deg:
            next_pan = self.pan_max_deg
            self.scan_direction = -1.0
        elif next_pan <= self.pan_min_deg:
            next_pan = self.pan_min_deg
            self.scan_direction = 1.0
        next_tilt = clamp(self.scan_tilt_deg, self.tilt_min_deg, self.tilt_max_deg)
        return next_pan, next_tilt

    def track_angles(self, detection):
        bbox = detection.bbox
        center_x = 0.5 * (float(bbox.xmin) + float(bbox.xmax))
        center_y = 0.5 * (float(bbox.ymin) + float(bbox.ymax))
        error_x = (center_x - self.image_width * 0.5) / max(self.image_width * 0.5, 1.0)
        error_y = (center_y - self.image_height * 0.5) / max(self.image_height * 0.5, 1.0)

        pan_delta = self.step_from_error(error_x)
        tilt_delta = self.step_from_error(error_y)
        next_pan = clamp(self.pan_deg + pan_delta, self.pan_min_deg, self.pan_max_deg)
        next_tilt = clamp(self.tilt_deg - tilt_delta, self.tilt_min_deg, self.tilt_max_deg)
        return next_pan, next_tilt

    def step_from_error(self, error):
        if abs(error) < self.center_deadband:
            return 0.0
        return clamp(error * self.track_gain_deg, -self.max_track_step_deg, self.max_track_step_deg)


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
