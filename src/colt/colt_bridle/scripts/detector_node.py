#!/usr/bin/env python3
"""Run Colt realtime detection with a compact ROS wrapper."""

import argparse
import json
from pathlib import Path

import message_filters
import rospy
from colt_msgs.msg import Detection3DArray
from sensor_msgs.msg import CameraInfo, Image
from std_msgs.msg import Header, String

from bridle_common import bgr8_to_image, image_to_bgr8, image_to_depth
from detector_pipeline import DetectorPipeline, RuntimeConfig


class DetectorNode:
    def __init__(self):
        runtime_dir = rospy.get_param("~runtime_dir", "")
        if not runtime_dir:
            runtime_dir = Path(__file__).resolve().parents[1] / "models" / "runtime" / "current"

        self.target_frame = rospy.get_param("~target_frame", "map")
        self.robot_frame = rospy.get_param("~robot_frame", "body_link")
        self.min_period = 1.0 / max(float(rospy.get_param("~detection_rate_hz", 2.0)), 0.1)
        self.last_process_time = rospy.Time(0)
        self.selection = {"source": "", "target": ""}
        self.pipeline = DetectorPipeline(
            runtime_dir=runtime_dir,
            target_frame=self.target_frame,
            robot_frame=self.robot_frame,
            max_chairs=int(rospy.get_param("~max_chairs", 8)),
            min_depth_pixels=int(rospy.get_param("~min_depth_pixels", 5)),
            max_chair_match_distance=float(rospy.get_param("~max_chair_match_distance", 0.8)),
        )

        self.detections_pub = rospy.Publisher("/colt/bridle/detections", Detection3DArray, queue_size=1)
        self.debug_pub = rospy.Publisher("/colt/bridle/debug_image", Image, queue_size=1)
        self.sync = self._build_sync()
        rospy.Subscriber("/colt/ui/selected_source_chair", String, self.selection_cb("source"), queue_size=1)
        rospy.Subscriber("/colt/ui/selected_target_chair", String, self.selection_cb("target"), queue_size=1)

        rospy.loginfo(
            "Colt detector ready: runtime=%s target_frame=%s robot_frame=%s",
            self.pipeline.config.runtime_dir,
            self.target_frame,
            self.robot_frame,
        )

    def _build_sync(self):
        color_topic = rospy.get_param("~color_topic", "/kinect2/qhd/image_color_rect")
        depth_topic = rospy.get_param("~depth_topic", "/kinect2/qhd/image_depth_rect")
        camera_info_topic = rospy.get_param("~camera_info_topic", "/kinect2/qhd/camera_info")
        sync = message_filters.ApproximateTimeSynchronizer(
            [
                message_filters.Subscriber(color_topic, Image),
                message_filters.Subscriber(depth_topic, Image),
                message_filters.Subscriber(camera_info_topic, CameraInfo),
            ],
            queue_size=int(rospy.get_param("~sync_queue_size", 5)),
            slop=float(rospy.get_param("~sync_slop", 0.08)),
        )
        sync.registerCallback(self.frame_cb)
        return sync

    def selection_cb(self, role):
        def callback(msg):
            self.selection[role] = msg.data.strip()

        return callback

    def frame_cb(self, color_msg, depth_msg, info_msg):
        now = rospy.Time.now()
        if (now - self.last_process_time).to_sec() < self.min_period:
            return
        self.last_process_time = now

        try:
            color = image_to_bgr8(color_msg)
            depth = image_to_depth(depth_msg)
            items = self.pipeline.detect(color, depth, info_msg, color_msg.header, dict(self.selection))
            self.publish_outputs(color, color_msg.header, items)
        except Exception as exc:
            rospy.logerr_throttle(5.0, "Colt detector failed: %s", exc)

    def publish_outputs(self, color, color_header, items):
        msg = Detection3DArray()
        msg.header = Header(stamp=color_header.stamp, frame_id=self.target_frame)
        msg.detections = [item["message"] for item in items]
        msg.scene_state = "active" if items else "empty"
        self.detections_pub.publish(msg)

        debug = self.pipeline.annotate(color, items)
        self.debug_pub.publish(bgr8_to_image(debug, color_header))


def check_runtime(runtime_dir):
    config = RuntimeConfig(runtime_dir)
    result = {
        "runtime_dir": str(config.runtime_dir),
        "errors": config.validate(),
        "ready": False,
    }
    result["ready"] = not result["errors"]
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ready"] else 2


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", default="", help="Validate runtime package and exit.")
    args, _ = parser.parse_known_args()
    if args.check:
        raise SystemExit(check_runtime(args.check))

    rospy.init_node("colt_detector")
    DetectorNode()
    rospy.spin()


if __name__ == "__main__":
    main()
