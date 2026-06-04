#!/usr/bin/env python3
"""Upload Colt ROS state snapshots to an HTTP server."""

import json
import math
import time
import urllib.error
import urllib.request

import rospy
import tf2_ros
from colt_msgs.msg import Detection3DArray
from std_msgs.msg import String, UInt8


def stamp_to_float(stamp):
    if stamp == rospy.Time(0):
        return 0.0
    return float(stamp.secs) + float(stamp.nsecs) * 1e-9


def yaw_from_quaternion(quat):
    siny_cosp = 2.0 * (float(quat.w) * float(quat.z) + float(quat.x) * float(quat.y))
    cosy_cosp = 1.0 - 2.0 * (float(quat.y) ** 2 + float(quat.z) ** 2)
    return math.atan2(siny_cosp, cosy_cosp)


def bbox_dict(bbox):
    return {
        "xmin": int(bbox.xmin),
        "ymin": int(bbox.ymin),
        "xmax": int(bbox.xmax),
        "ymax": int(bbox.ymax),
    }


def detection_dict(item):
    return {
        "id": item.id,
        "parent_id": item.parent_id,
        "object_type": item.object_type,
        "role": item.role,
        "state": int(item.state),
        "confidence": float(item.confidence),
        "frame_id": item.header.frame_id,
        "x": float(item.x),
        "y": float(item.y),
        "z": float(item.z),
        "bbox": bbox_dict(item.bbox),
    }


class TelemetryUploader:
    def __init__(self):
        self.server_url = rospy.get_param("~server_url", "").strip()
        self.upload_token = rospy.get_param("~upload_token", "").strip()
        self.upload_rate_hz = float(rospy.get_param("~upload_rate_hz", 1.0))
        self.target_frame = rospy.get_param("~target_frame", "map")
        self.robot_frame = rospy.get_param("~robot_frame", "body_link")
        self.http_timeout_sec = float(rospy.get_param("~http_timeout_sec", 1.5))
        self.tf_timeout_sec = float(rospy.get_param("~tf_timeout_sec", 0.05))

        self.detections_topic = rospy.get_param("~detections_topic", "/colt/bridle/detections")
        self.source_topic = rospy.get_param("~source_topic", "/colt/ui/selected_source_chair")
        self.target_topic = rospy.get_param("~target_topic", "/colt/ui/selected_target_chair")
        self.pt_state_topic = rospy.get_param("~pt_state_topic", "/colt/ui/pt_state")

        self.latest_detections = None
        self.latest_detections_time = rospy.Time(0)
        self.selection = {"source": "", "target": "", "pt_state": 0}

        self.tf_buffer = tf2_ros.Buffer(cache_time=rospy.Duration(5.0))
        self.tf_listener = tf2_ros.TransformListener(self.tf_buffer)

        rospy.Subscriber(self.detections_topic, Detection3DArray, self.detections_cb, queue_size=1)
        rospy.Subscriber(self.source_topic, String, self.source_cb, queue_size=1)
        rospy.Subscriber(self.target_topic, String, self.target_cb, queue_size=1)
        rospy.Subscriber(self.pt_state_topic, UInt8, self.pt_state_cb, queue_size=1)

        if not self.server_url:
            rospy.logwarn("paddock telemetry uploader started without server_url; snapshots will not be uploaded")

        period = 1.0 / max(self.upload_rate_hz, 0.1)
        rospy.Timer(rospy.Duration(period), self.upload_tick)

    def detections_cb(self, msg):
        self.latest_detections = msg
        self.latest_detections_time = rospy.Time.now()

    def source_cb(self, msg):
        self.selection["source"] = msg.data.strip()

    def target_cb(self, msg):
        self.selection["target"] = msg.data.strip()

    def pt_state_cb(self, msg):
        self.selection["pt_state"] = int(msg.data)

    def upload_tick(self, _event):
        snapshot = self.build_snapshot()
        if not self.server_url:
            rospy.logwarn_throttle(10.0, "Paddock telemetry has no server_url; latest snapshot not uploaded")
            return
        self.post_snapshot(snapshot)

    def build_snapshot(self):
        now = rospy.Time.now()
        detections = self.latest_detections
        detections_age = None
        objects = []
        scene_state = ""
        detections_stamp = 0.0
        if detections is not None:
            detections_age = max(0.0, (now - self.latest_detections_time).to_sec())
            detections_stamp = stamp_to_float(detections.header.stamp)
            scene_state = detections.scene_state
            objects = [detection_dict(item) for item in detections.detections]

        return {
            "robot": self.robot_state(now),
            "selection": dict(self.selection),
            "objects": objects,
            "health": {
                "stamp": stamp_to_float(now),
                "upload_time": time.time(),
                "detections_stamp": detections_stamp,
                "detections_age_sec": detections_age,
                "scene_state": scene_state,
            },
        }

    def robot_state(self, stamp):
        try:
            transform = self.tf_buffer.lookup_transform(
                self.target_frame,
                self.robot_frame,
                rospy.Time(0),
                timeout=rospy.Duration(self.tf_timeout_sec),
            )
        except Exception:
            rospy.logwarn_throttle(
                5.0,
                "Paddock telemetry TF unavailable: %s <- %s",
                self.target_frame,
                self.robot_frame,
            )
            return {
                "frame_id": self.target_frame,
                "x": 0.0,
                "y": 0.0,
                "yaw": 0.0,
                "tf_ok": False,
                "stamp": stamp_to_float(stamp),
            }

        trans = transform.transform.translation
        rot = transform.transform.rotation
        return {
            "frame_id": transform.header.frame_id or self.target_frame,
            "x": float(trans.x),
            "y": float(trans.y),
            "yaw": yaw_from_quaternion(rot),
            "tf_ok": True,
            "stamp": stamp_to_float(transform.header.stamp),
        }

    def post_snapshot(self, snapshot):
        data = json.dumps(snapshot, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
        request = urllib.request.Request(
            self.server_url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "paddock-telemetry/0.1",
            },
            method="POST",
        )
        if self.upload_token:
            request.add_header("Authorization", f"Bearer {self.upload_token}")

        try:
            with urllib.request.urlopen(request, timeout=self.http_timeout_sec) as response:
                status = int(response.getcode())
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            rospy.logwarn_throttle(5.0, "Paddock telemetry upload failed: %s", exc)
            return

        if status < 200 or status >= 300:
            rospy.logwarn_throttle(5.0, "Paddock telemetry upload returned HTTP %d", status)
            return
        rospy.loginfo_throttle(10.0, "Paddock telemetry uploaded to %s", self.server_url)


def main():
    rospy.init_node("paddock_telemetry_uploader")
    TelemetryUploader()
    rospy.loginfo("Paddock telemetry uploader ready")
    rospy.spin()


if __name__ == "__main__":
    main()
