#!/usr/bin/env python3
"""Continuously upload simulated Paddock telemetry snapshots."""

import json
import math
import time
import urllib.error
import urllib.request

import rospy


DEFAULT_SERVER_URL = "http://20.194.24.158:2100/api/telemetry"


def stamp_to_float(stamp):
    if stamp == rospy.Time(0):
        return 0.0
    return float(stamp.secs) + float(stamp.nsecs) * 1e-9


def clamp_int(value, low, high):
    return int(max(low, min(high, round(value))))


def bbox(center_x, center_y, width, height):
    half_w = width * 0.5
    half_h = height * 0.5
    return {
        "xmin": clamp_int(center_x - half_w, 0, 960),
        "ymin": clamp_int(center_y - half_h, 0, 540),
        "xmax": clamp_int(center_x + half_w, 0, 960),
        "ymax": clamp_int(center_y + half_h, 0, 540),
    }


class TelemetrySimulator:
    def __init__(self):
        self.server_url = rospy.get_param("~server_url", DEFAULT_SERVER_URL).strip()
        self.upload_token = rospy.get_param("~upload_token", "").strip()
        self.upload_rate_hz = float(rospy.get_param("~upload_rate_hz", 1.0))
        self.frame_id = rospy.get_param("~frame_id", "map")
        self.http_timeout_sec = float(rospy.get_param("~http_timeout_sec", 1.5))
        self.start_time = time.time()

        if not self.server_url:
            rospy.logwarn("paddock telemetry simulator started without server_url; snapshots will not be uploaded")

    def spin(self):
        rate = rospy.Rate(max(self.upload_rate_hz, 0.1))
        while not rospy.is_shutdown():
            snapshot = self.build_snapshot()
            if not self.server_url:
                rospy.logwarn_throttle(10.0, "Paddock telemetry simulator has no server_url")
            else:
                self.post_snapshot(snapshot)
            rate.sleep()

    def elapsed(self):
        return max(0.0, time.time() - self.start_time)

    def build_snapshot(self):
        t = self.elapsed()
        now = rospy.Time.now()
        stamp = stamp_to_float(now)
        pt_state = 0 if int(t // 20.0) % 2 == 0 else 1

        return {
            "robot": self.robot_state(t, stamp),
            "selection": {
                "source": "chair_0",
                "target": "chair_1",
                "pt_state": pt_state,
            },
            "objects": self.objects(t),
            "health": {
                "stamp": stamp,
                "upload_time": time.time(),
                "detections_stamp": stamp,
                "detections_age_sec": 0.0,
                "scene_state": "simulated_site",
            },
        }

    def robot_state(self, t, stamp):
        return {
            "frame_id": self.frame_id,
            "x": 0.55 + 0.08 * math.sin(t / 8.0),
            "y": -0.20 + 0.05 * math.cos(t / 11.0),
            "yaw": 0.20 * math.sin(t / 10.0),
            "tf_ok": True,
            "stamp": stamp,
        }

    def objects(self, t):
        source_lost = 22 <= int(t) % 36 < 27
        target_no_depth = 14 <= int(t) % 30 < 19
        normal_lost = int(t) % 18 >= 12
        shift = 18.0 * math.sin(t / 5.0)

        source_state = 0 if source_lost else 1
        target_state = 2 if target_no_depth else 1
        normal_state = 0 if normal_lost else 1

        return [
            self.object_dict(
                "chair_0",
                "",
                "chair",
                "source",
                source_state,
                0.95,
                1.20,
                0.35,
                0.0,
                bbox(340 + shift, 255, 170, 285),
            ),
            self.object_dict(
                "chair_0_seat",
                "chair_0",
                "seat",
                "source",
                source_state,
                0.90,
                1.18,
                0.34,
                0.45,
                bbox(345 + shift, 305, 125, 130),
            ),
            self.object_dict(
                "chair_0_item",
                "chair_0",
                "item",
                "source",
                source_state,
                0.88,
                1.17,
                0.33,
                0.78,
                bbox(380 + shift, 215, 54, 65),
            ),
            self.object_dict(
                "chair_1",
                "",
                "chair",
                "target",
                target_state,
                0.93,
                1.72,
                -0.42,
                0.0,
                bbox(635 - shift * 0.4, 262, 165, 275),
            ),
            self.object_dict(
                "chair_1_seat",
                "chair_1",
                "seat",
                "target",
                target_state,
                0.86,
                1.70,
                -0.42,
                0.45,
                bbox(638 - shift * 0.4, 310, 118, 124),
            ),
            self.object_dict(
                "chair_2",
                "",
                "chair",
                "normal",
                normal_state,
                0.78,
                2.05,
                0.80,
                0.0,
                bbox(790, 278, 140, 260),
            ),
        ]

    def object_dict(self, object_id, parent_id, object_type, role, state, confidence, x, y, z, box):
        if state == 0:
            confidence = 0.0
            box = bbox(0, 0, 0, 0)
        return {
            "id": object_id,
            "parent_id": parent_id,
            "object_type": object_type,
            "role": role,
            "state": int(state),
            "confidence": float(confidence),
            "frame_id": self.frame_id,
            "x": float(x),
            "y": float(y),
            "z": float(z),
            "bbox": box,
        }

    def post_snapshot(self, snapshot):
        data = json.dumps(snapshot, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
        request = urllib.request.Request(
            self.server_url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "paddock-telemetry-simulator/0.1",
            },
            method="POST",
        )
        if self.upload_token:
            request.add_header("Authorization", f"Bearer {self.upload_token}")

        try:
            with urllib.request.urlopen(request, timeout=self.http_timeout_sec) as response:
                status = int(response.getcode())
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            rospy.logwarn_throttle(5.0, "Paddock telemetry simulator upload failed: %s", exc)
            return False

        if status < 200 or status >= 300:
            rospy.logwarn_throttle(5.0, "Paddock telemetry simulator returned HTTP %d", status)
            return False
        rospy.loginfo_throttle(5.0, "Paddock telemetry simulator uploaded to %s", self.server_url)
        return True


def main():
    rospy.init_node("paddock_telemetry_simulator")
    simulator = TelemetrySimulator()
    rospy.loginfo("Paddock telemetry simulator ready")
    simulator.spin()


if __name__ == "__main__":
    main()
