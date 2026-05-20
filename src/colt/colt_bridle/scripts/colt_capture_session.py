#!/usr/bin/env python3
"""Capture synchronized Kinect2 frames into a Windows-readable session folder."""

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
import rosgraph
import rospy
import yaml
from cv_bridge import CvBridge
from sensor_msgs.msg import CameraInfo, Image, JointState, PointCloud2
from tf2_msgs.msg import TFMessage


CONTROL_TOPICS = [
    "/cmd_vel",
    "/wpv4_pt/joint_ctrl_degree",
    "/wpv4_pt/joint_ctrl_radian",
    "/wpm2/joint_ctrl_degree",
    "/wpv4/grab_obj",
    "/wpv4/behaviors",
]


def time_to_float(stamp):
    return float(stamp.secs) + float(stamp.nsecs) * 1e-9


def header_to_dict(header):
    return {
        "seq": int(header.seq),
        "stamp": time_to_float(header.stamp),
        "frame_id": header.frame_id,
    }


def vector3_to_dict(value):
    return {"x": float(value.x), "y": float(value.y), "z": float(value.z)}


def quaternion_to_dict(value):
    return {
        "x": float(value.x),
        "y": float(value.y),
        "z": float(value.z),
        "w": float(value.w),
    }


def transform_to_dict(transform):
    return {
        "header": header_to_dict(transform.header),
        "child_frame_id": transform.child_frame_id,
        "translation": vector3_to_dict(transform.transform.translation),
        "rotation": quaternion_to_dict(transform.transform.rotation),
    }


def joint_state_to_dict(msg):
    if msg is None:
        return None
    return {
        "header": header_to_dict(msg.header),
        "name": list(msg.name),
        "position": [float(v) for v in msg.position],
        "velocity": [float(v) for v in msg.velocity],
        "effort": [float(v) for v in msg.effort],
    }


def camera_info_to_dict(msg):
    return {
        "header": header_to_dict(msg.header),
        "height": int(msg.height),
        "width": int(msg.width),
        "distortion_model": msg.distortion_model,
        "D": [float(v) for v in msg.D],
        "K": [float(v) for v in msg.K],
        "R": [float(v) for v in msg.R],
        "P": [float(v) for v in msg.P],
        "binning_x": int(msg.binning_x),
        "binning_y": int(msg.binning_y),
        "roi": {
            "x_offset": int(msg.roi.x_offset),
            "y_offset": int(msg.roi.y_offset),
            "height": int(msg.roi.height),
            "width": int(msg.roi.width),
            "do_rectify": bool(msg.roi.do_rectify),
        },
    }


def pointcloud_to_npz(path, msg):
    fields = msg.fields
    np.savez_compressed(
        path,
        data=np.frombuffer(msg.data, dtype=np.uint8),
        header=json.dumps(header_to_dict(msg.header), ensure_ascii=True),
        height=np.array(msg.height, dtype=np.uint32),
        width=np.array(msg.width, dtype=np.uint32),
        is_bigendian=np.array(msg.is_bigendian, dtype=np.bool_),
        point_step=np.array(msg.point_step, dtype=np.uint32),
        row_step=np.array(msg.row_step, dtype=np.uint32),
        is_dense=np.array(msg.is_dense, dtype=np.bool_),
        field_names=np.array([field.name for field in fields]),
        field_offsets=np.array([field.offset for field in fields], dtype=np.uint32),
        field_datatypes=np.array([field.datatype for field in fields], dtype=np.uint8),
        field_counts=np.array([field.count for field in fields], dtype=np.uint32),
    )


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

    def __exit__(self, exc_type, exc, tb):
        if self.enabled and self.old_settings is not None:
            termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old_settings)

    def read_key(self):
        if not self.enabled:
            return None
        ready, _, _ = select.select([sys.stdin], [], [], 0.0)
        if not ready:
            return None
        return sys.stdin.read(1)


class CaptureSession:
    def __init__(self):
        self.bridge = CvBridge()
        self.lock = threading.Lock()
        self.latest_frame = None
        self.latest_tf = None
        self.latest_tf_static = None
        self.latest_joint_states = None
        self.latest_raw_joint_states = None
        self.running = bool(rospy.get_param("~auto_start", False))
        self.finished = False
        self.frame_count = 0
        self.last_captured_stamp = None
        self.scene_tags = set()

        self.output_root = os.path.expanduser(
            rospy.get_param("~output_root", os.path.join("~", "colt_capture_sessions"))
        )
        self.session_id = rospy.get_param("~session_id", "")
        if not self.session_id:
            self.session_id = datetime.now().strftime("session_%Y%m%d_%H%M%S")
        self.session_dir = os.path.join(self.output_root, self.session_id)

        self.capture_rate_hz = float(rospy.get_param("~capture_rate_hz", 2.0))
        self.max_frames = int(rospy.get_param("~max_frames", 0))
        self.max_frame_age_s = float(rospy.get_param("~max_frame_age_s", 1.0))
        self.save_points = bool(rospy.get_param("~save_points", True))
        self.save_preview = bool(rospy.get_param("~save_preview", True))
        self.keyboard_enabled = bool(rospy.get_param("~keyboard", True))

        self.topics = {
            "color": rospy.get_param("~color_topic", "/kinect2/qhd/image_color_rect"),
            "depth": rospy.get_param("~depth_topic", "/kinect2/qhd/image_depth_rect"),
            "points": rospy.get_param("~points_topic", "/kinect2/qhd/points"),
            "camera_info": rospy.get_param("~camera_info_topic", "/kinect2/qhd/camera_info"),
            "tf": rospy.get_param("~tf_topic", "/tf"),
            "tf_static": rospy.get_param("~tf_static_topic", "/tf_static"),
            "joint_states": rospy.get_param("~joint_states_topic", "/joint_states"),
            "raw_joint_states": rospy.get_param(
                "~raw_joint_states_topic", "/wpv4_pt/raw_joint_states"
            ),
        }

        self.control_publishers = self.get_control_publishers()
        if self.control_publishers.get("/cmd_vel") and self.running:
            rospy.logwarn("/cmd_vel has publishers; forcing capture to paused state")
            self.running = False

        self.create_session_dirs()
        self.meta_file = open(
            os.path.join(self.session_dir, "meta.jsonl"), "a", encoding="utf-8"
        )
        self.write_session_yaml(final=False)

        self.setup_subscribers()
        rospy.Timer(rospy.Duration(1.0 / self.capture_rate_hz), self.capture_tick)

    def create_session_dirs(self):
        for name in [
            "images",
            "depth",
            "points",
            "camera_info",
            "tf",
            "preview",
        ]:
            os.makedirs(os.path.join(self.session_dir, name), exist_ok=True)

    def get_control_publishers(self):
        result = {topic: [] for topic in CONTROL_TOPICS}
        try:
            master = rosgraph.Master(rospy.get_name())
            publishers, _, _ = master.getSystemState()
            for topic, nodes in publishers:
                if topic in result:
                    result[topic] = list(nodes)
        except Exception as exc:  # pragma: no cover - only depends on ROS master state.
            rospy.logwarn("Could not query ROS master publishers: %s", exc)
        return result

    def setup_subscribers(self):
        color_sub = message_filters.Subscriber(self.topics["color"], Image)
        depth_sub = message_filters.Subscriber(self.topics["depth"], Image)
        points_sub = message_filters.Subscriber(self.topics["points"], PointCloud2)
        camera_info_sub = message_filters.Subscriber(self.topics["camera_info"], CameraInfo)
        sync = message_filters.ApproximateTimeSynchronizer(
            [color_sub, depth_sub, points_sub, camera_info_sub],
            queue_size=int(rospy.get_param("~sync_queue_size", 10)),
            slop=float(rospy.get_param("~sync_slop", 0.08)),
        )
        sync.registerCallback(self.frame_callback)

        rospy.Subscriber(self.topics["tf"], TFMessage, self.tf_callback, queue_size=50)
        rospy.Subscriber(
            self.topics["tf_static"], TFMessage, self.tf_static_callback, queue_size=10
        )
        rospy.Subscriber(
            self.topics["joint_states"], JointState, self.joint_states_callback, queue_size=10
        )
        rospy.Subscriber(
            self.topics["raw_joint_states"],
            JointState,
            self.raw_joint_states_callback,
            queue_size=10,
        )

    def frame_callback(self, color, depth, points, camera_info):
        with self.lock:
            self.latest_frame = {
                "color": color,
                "depth": depth,
                "points": points,
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

    def raw_joint_states_callback(self, msg):
        with self.lock:
            self.latest_raw_joint_states = msg

    def handle_key(self, key):
        if key is None:
            return
        if key == "s":
            self.running = True
            rospy.loginfo("Capture resumed")
        elif key == "p":
            self.running = False
            rospy.loginfo("Capture paused")
        elif key == "q":
            self.finished = True
            rospy.signal_shutdown("capture finished by keyboard")
        elif key == "1":
            self.toggle_tag("source_chair")
        elif key == "2":
            self.toggle_tag("target_chair")
        elif key == "a":
            self.scene_tags.discard("aluminum_absent")
            self.scene_tags.add("aluminum_present")
            rospy.loginfo("Scene tags: %s", sorted(self.scene_tags))
        elif key == "n":
            self.scene_tags.discard("aluminum_present")
            self.scene_tags.add("aluminum_absent")
            rospy.loginfo("Scene tags: %s", sorted(self.scene_tags))
        elif key == "m":
            self.toggle_tag("motion_approach")
        elif key == "o":
            self.toggle_tag("arm_occlusion")

    def toggle_tag(self, tag):
        if tag in self.scene_tags:
            self.scene_tags.remove(tag)
        else:
            self.scene_tags.add(tag)
        rospy.loginfo("Scene tags: %s", sorted(self.scene_tags))

    def capture_tick(self, _event):
        if not self.running or self.finished:
            return
        with self.lock:
            frame = dict(self.latest_frame) if self.latest_frame else None
            latest_tf = self.latest_tf
            latest_tf_static = self.latest_tf_static
            latest_joint_states = self.latest_joint_states
            latest_raw_joint_states = self.latest_raw_joint_states

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
        frame_id = self.frame_count
        frame_name = f"{frame_id:06d}"
        try:
            metadata = self.save_frame(
                frame_name,
                frame,
                latest_tf,
                latest_tf_static,
                latest_joint_states,
                latest_raw_joint_states,
            )
            self.meta_file.write(json.dumps(metadata, ensure_ascii=True) + "\n")
            self.meta_file.flush()
            self.last_captured_stamp = stamp
            rospy.loginfo("Captured frame %s tags=%s", frame_name, sorted(self.scene_tags))
        except Exception as exc:
            rospy.logerr("Failed to save frame %s: %s", frame_name, exc)
            self.frame_count -= 1
            return

        if self.max_frames > 0 and self.frame_count >= self.max_frames:
            self.finished = True
            rospy.signal_shutdown("capture reached max_frames")

    def save_frame(
        self,
        frame_name,
        frame,
        latest_tf,
        latest_tf_static,
        latest_joint_states,
        latest_raw_joint_states,
    ):
        color_path = os.path.join("images", f"{frame_name}.png")
        depth_path = os.path.join("depth", f"{frame_name}.npy")
        points_path = os.path.join("points", f"{frame_name}.npz")
        camera_info_path = os.path.join("camera_info", f"{frame_name}.yaml")
        tf_path = os.path.join("tf", f"{frame_name}.yaml")
        preview_path = os.path.join("preview", f"{frame_name}.jpg")

        color = self.bridge.imgmsg_to_cv2(frame["color"], desired_encoding="bgr8")
        depth = self.bridge.imgmsg_to_cv2(frame["depth"], desired_encoding="passthrough")

        cv2.imwrite(os.path.join(self.session_dir, color_path), color)
        np.save(os.path.join(self.session_dir, depth_path), depth)
        if self.save_points:
            pointcloud_to_npz(os.path.join(self.session_dir, points_path), frame["points"])
        else:
            points_path = ""

        with open(os.path.join(self.session_dir, camera_info_path), "w", encoding="utf-8") as f:
            yaml.safe_dump(camera_info_to_dict(frame["camera_info"]), f, sort_keys=False)

        tf_data = {
            "tf_available": latest_tf is not None,
            "tf_static_available": latest_tf_static is not None,
            "tf": [transform_to_dict(t) for t in latest_tf.transforms] if latest_tf else [],
            "tf_static": (
                [transform_to_dict(t) for t in latest_tf_static.transforms]
                if latest_tf_static
                else []
            ),
        }
        with open(os.path.join(self.session_dir, tf_path), "w", encoding="utf-8") as f:
            yaml.safe_dump(tf_data, f, sort_keys=False)

        if self.save_preview:
            preview = color.copy()
            cv2.putText(
                preview,
                f"{frame_name} {' '.join(sorted(self.scene_tags))}",
                (16, 32),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 255, 255),
                2,
                cv2.LINE_AA,
            )
            cv2.imwrite(os.path.join(self.session_dir, preview_path), preview)
        else:
            preview_path = ""

        stamp = time_to_float(frame["color"].header.stamp)
        return {
            "frame_id": int(self.frame_count),
            "stamp": stamp,
            "saved_at": time_to_float(rospy.Time.now()),
            "image": color_path,
            "depth": depth_path,
            "points": points_path,
            "camera_info": camera_info_path,
            "tf": tf_path,
            "preview": preview_path,
            "scene_tags": sorted(self.scene_tags),
            "tf_available": latest_tf is not None,
            "tf_static_available": latest_tf_static is not None,
            "color_header": header_to_dict(frame["color"].header),
            "depth_header": header_to_dict(frame["depth"].header),
            "points_header": header_to_dict(frame["points"].header),
            "camera_info_header": header_to_dict(frame["camera_info"].header),
            "joint_states": joint_state_to_dict(latest_joint_states),
            "raw_joint_states": joint_state_to_dict(latest_raw_joint_states),
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
            "save_points": self.save_points,
            "save_preview": self.save_preview,
            "control_topic_publishers_at_start": self.control_publishers,
            "safety": {
                "publishes_cmd_vel": False,
                "publishes_pt_command": False,
                "publishes_arm_or_grasp_command": False,
            },
            "keyboard": {
                "s": "start_or_resume",
                "p": "pause",
                "q": "finish",
                "1": "toggle_source_chair",
                "2": "toggle_target_chair",
                "a": "mark_aluminum_present",
                "n": "mark_aluminum_absent",
                "m": "toggle_motion_approach",
                "o": "toggle_arm_occlusion",
            },
        }
        os.makedirs(self.session_dir, exist_ok=True)
        with open(os.path.join(self.session_dir, "session.yaml"), "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, sort_keys=False)

    def close(self):
        self.write_session_yaml(final=True)
        self.meta_file.close()


def main():
    rospy.init_node("colt_capture_session")
    session = CaptureSession()
    rospy.loginfo("Capture session directory: %s", session.session_dir)
    rospy.loginfo("Keyboard: s=start p=pause q=finish 1/2/a/n/m/o=scene tags")
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
