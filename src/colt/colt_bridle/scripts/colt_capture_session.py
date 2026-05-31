#!/usr/bin/env python3
"""Minimal synchronized RGB/depth/camera_info capture for Colt."""

import json
import os
import select
import sys
import termios
import threading
import tty
from datetime import datetime

import cv2
import message_filters
import numpy as np
import rospy
import yaml
from bridle_common import (
    camera_info_to_dict,
    header_to_dict,
    image_to_bgr8,
    image_to_depth,
    joint_state_to_dict,
    time_to_float,
    transform_to_dict,
)
from sensor_msgs.msg import CameraInfo, Image, JointState
from tf2_msgs.msg import TFMessage


class KeyboardReader:
    def __init__(self, enabled):
        self.enabled = enabled and sys.stdin.isatty()
        self.fd = None
        self.old_settings = None

    def __enter__(self):
        if self.enabled:
            self.fd = sys.stdin.fileno()
            self.old_settings = termios.tcgetattr(self.fd)
            tty.setcbreak(self.fd)
        return self

    def __exit__(self, _exc_type, _exc, _tb):
        if self.enabled and self.old_settings is not None:
            termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old_settings)

    def read_key(self):
        if not self.enabled:
            return None
        ready, _, _ = select.select([sys.stdin], [], [], 0.0)
        return sys.stdin.read(1) if ready else None


class CaptureSession:
    def __init__(self):
        self.lock = threading.Lock()
        self.latest_frame = None
        self.latest_tf = None
        self.latest_tf_static = None
        self.latest_joint_states = None
        self.running = bool(rospy.get_param("~auto_start", False))
        self.finished = False
        self.frame_count = 0
        self.last_captured_stamp = None

        self.output_root = os.path.expanduser(rospy.get_param("~output_root", os.path.join("~", "colt_capture_sessions")))
        self.session_id = rospy.get_param("~session_id", "") or datetime.now().strftime("session_%Y%m%d_%H%M%S")
        self.session_dir = os.path.join(self.output_root, self.session_id)
        self.capture_rate_hz = float(rospy.get_param("~capture_rate_hz", 2.0))
        self.max_frames = int(rospy.get_param("~max_frames", 0))
        self.max_frame_age_s = float(rospy.get_param("~max_frame_age_s", 1.0))
        self.keyboard_enabled = bool(rospy.get_param("~keyboard", True))

        self.topics = {
            "color": rospy.get_param("~color_topic", "/kinect2/qhd/image_color_rect"),
            "depth": rospy.get_param("~depth_topic", "/kinect2/qhd/image_depth_rect"),
            "camera_info": rospy.get_param("~camera_info_topic", "/kinect2/qhd/camera_info"),
            "tf": rospy.get_param("~tf_topic", "/tf"),
            "tf_static": rospy.get_param("~tf_static_topic", "/tf_static"),
            "joint_states": rospy.get_param("~joint_states_topic", "/joint_states"),
        }

        self.create_session_dirs()
        self.meta_file = open(os.path.join(self.session_dir, "meta.jsonl"), "a", encoding="utf-8")
        self.write_session_yaml(final=False)
        self.setup_subscribers()
        rospy.Timer(rospy.Duration(1.0 / self.capture_rate_hz), self.capture_tick)

    def create_session_dirs(self):
        for name in ("images", "depth", "camera_info", "tf"):
            os.makedirs(os.path.join(self.session_dir, name), exist_ok=True)

    def setup_subscribers(self):
        color_sub = message_filters.Subscriber(self.topics["color"], Image)
        depth_sub = message_filters.Subscriber(self.topics["depth"], Image)
        camera_info_sub = message_filters.Subscriber(self.topics["camera_info"], CameraInfo)
        sync = message_filters.ApproximateTimeSynchronizer(
            [color_sub, depth_sub, camera_info_sub],
            queue_size=int(rospy.get_param("~sync_queue_size", 10)),
            slop=float(rospy.get_param("~sync_slop", 0.08)),
        )
        sync.registerCallback(self.frame_callback)
        rospy.Subscriber(self.topics["tf"], TFMessage, self.tf_callback, queue_size=50)
        rospy.Subscriber(self.topics["tf_static"], TFMessage, self.tf_static_callback, queue_size=10)
        rospy.Subscriber(self.topics["joint_states"], JointState, self.joint_states_callback, queue_size=10)

    def frame_callback(self, color, depth, camera_info):
        with self.lock:
            self.latest_frame = {
                "color": color,
                "depth": depth,
                "camera_info": camera_info,
                "received_at": rospy.Time.now(),
            }

    def tf_callback(self, msg):
        with self.lock:
            self.latest_tf = msg

    def tf_static_callback(self, msg):
        with self.lock:
            self.latest_tf_static = msg

    def joint_states_callback(self, msg):
        with self.lock:
            self.latest_joint_states = msg

    def handle_key(self, key):
        if key == "s":
            self.running = True
            rospy.loginfo("Capture resumed")
        elif key == "p":
            self.running = False
            rospy.loginfo("Capture paused")
        elif key == "q":
            self.finished = True
            rospy.signal_shutdown("capture finished by keyboard")

    def capture_tick(self, _event):
        if not self.running or self.finished:
            return
        with self.lock:
            frame = dict(self.latest_frame) if self.latest_frame else None
            latest_tf = self.latest_tf
            latest_tf_static = self.latest_tf_static
            latest_joint_states = self.latest_joint_states

        if frame is None:
            rospy.logwarn_throttle(5.0, "Waiting for synchronized camera frame")
            return

        stamp = frame["color"].header.stamp
        if self.last_captured_stamp == stamp:
            return
        age = (rospy.Time.now() - frame["received_at"]).to_sec()
        if age > self.max_frame_age_s:
            rospy.logwarn_throttle(5.0, "Latest synchronized frame is stale: %.3f s", age)
            return

        self.frame_count += 1
        frame_name = f"{self.frame_count:06d}"
        try:
            metadata = self.save_frame(frame_name, frame, latest_tf, latest_tf_static, latest_joint_states)
            self.meta_file.write(json.dumps(metadata, ensure_ascii=True) + "\n")
            self.meta_file.flush()
            self.last_captured_stamp = stamp
            rospy.loginfo("Captured frame %s", frame_name)
        except Exception as exc:
            self.frame_count -= 1
            rospy.logerr("Failed to save frame %s: %s", frame_name, exc)
            return

        if self.max_frames > 0 and self.frame_count >= self.max_frames:
            self.finished = True
            rospy.signal_shutdown("capture reached max_frames")

    def save_frame(self, frame_name, frame, latest_tf, latest_tf_static, latest_joint_states):
        color_path = os.path.join("images", f"{frame_name}.png")
        depth_path = os.path.join("depth", f"{frame_name}.npy")
        camera_info_path = os.path.join("camera_info", f"{frame_name}.yaml")
        tf_path = os.path.join("tf", f"{frame_name}.yaml")

        cv2.imwrite(os.path.join(self.session_dir, color_path), image_to_bgr8(frame["color"]))
        np.save(os.path.join(self.session_dir, depth_path), image_to_depth(frame["depth"]))
        with open(os.path.join(self.session_dir, camera_info_path), "w", encoding="utf-8") as stream:
            yaml.safe_dump(camera_info_to_dict(frame["camera_info"]), stream, sort_keys=False)

        tf_data = {
            "tf_available": latest_tf is not None,
            "tf_static_available": latest_tf_static is not None,
            "tf": [transform_to_dict(item) for item in latest_tf.transforms] if latest_tf else [],
            "tf_static": [transform_to_dict(item) for item in latest_tf_static.transforms] if latest_tf_static else [],
        }
        with open(os.path.join(self.session_dir, tf_path), "w", encoding="utf-8") as stream:
            yaml.safe_dump(tf_data, stream, sort_keys=False)

        return {
            "frame_id": int(self.frame_count),
            "stamp": time_to_float(frame["color"].header.stamp),
            "saved_at": time_to_float(rospy.Time.now()),
            "image": color_path,
            "depth": depth_path,
            "camera_info": camera_info_path,
            "tf": tf_path,
            "color_header": header_to_dict(frame["color"].header),
            "depth_header": header_to_dict(frame["depth"].header),
            "camera_info_header": header_to_dict(frame["camera_info"].header),
            "joint_states": joint_state_to_dict(latest_joint_states),
        }

    def write_session_yaml(self, final):
        data = {
            "session_id": self.session_id,
            "session_dir": self.session_dir,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "final": bool(final),
            "frame_count": int(self.frame_count),
            "topics": self.topics,
            "capture_rate_hz": self.capture_rate_hz,
            "publishes_motion_commands": False,
            "keyboard": {"s": "start_or_resume", "p": "pause", "q": "finish"},
        }
        with open(os.path.join(self.session_dir, "session.yaml"), "w", encoding="utf-8") as stream:
            yaml.safe_dump(data, stream, sort_keys=False)

    def close(self):
        self.write_session_yaml(final=True)
        self.meta_file.close()


def main():
    rospy.init_node("colt_capture_session")
    session = CaptureSession()
    rospy.loginfo("Capture session directory: %s", session.session_dir)
    rospy.loginfo("Keyboard: s=start p=pause q=finish")
    rospy.loginfo("Initial capture state: %s", "running" if session.running else "paused")

    with KeyboardReader(session.keyboard_enabled) as keyboard:
        rate = rospy.Rate(20)
        while not rospy.is_shutdown():
            session.handle_key(keyboard.read_key())
            rate.sleep()

    session.close()
    rospy.loginfo("Capture session closed with %d frames", session.frame_count)


if __name__ == "__main__":
    main()
