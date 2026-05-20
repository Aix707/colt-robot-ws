#!/usr/bin/env python3
"""Minimal terminal UI for selecting Colt source and target chairs."""

import argparse
import sys
import threading

import rospy
from colt_msgs.msg import Detection3DArray
from std_msgs.msg import String


class TerminalChairSelector:
    def __init__(self, source_chair="", target_chair=""):
        self.lock = threading.Lock()
        self.candidates = {}
        self.input_topic = rospy.get_param("~input_topic", "/colt/bridle/candidates")
        self.prompt = bool(rospy.get_param("~prompt", True)) and sys.stdin.isatty()
        self.source_chair = source_chair.strip() or rospy.get_param("~source_chair", "").strip()
        self.target_chair = target_chair.strip() or rospy.get_param("~target_chair", "").strip()
        self.source_pub = rospy.Publisher(
            "/colt/ui/selected_source_chair", String, queue_size=1, latch=True
        )
        self.target_pub = rospy.Publisher(
            "/colt/ui/selected_target_chair", String, queue_size=1, latch=True
        )
        rospy.Subscriber(self.input_topic, Detection3DArray, self.candidates_cb, queue_size=10)

    def candidates_cb(self, msg):
        chairs = {}
        for detection in msg.detections:
            if detection.class_name != "chair":
                continue
            chairs[detection.id] = {
                "id": detection.id,
                "confidence": float(detection.confidence),
                "x": float(detection.pose.pose.position.x),
                "y": float(detection.pose.pose.position.y),
                "z": float(detection.pose.pose.position.z),
            }
        with self.lock:
            self.candidates = chairs

    def publish_current(self):
        if self.source_chair:
            self.source_pub.publish(String(data=self.source_chair))
            rospy.loginfo("Selected source chair: %s", self.source_chair)
        if self.target_chair:
            self.target_pub.publish(String(data=self.target_chair))
            rospy.loginfo("Selected target chair: %s", self.target_chair)

    def chair_ids(self):
        with self.lock:
            return sorted(self.candidates)

    def print_candidates(self):
        with self.lock:
            candidates = [self.candidates[key] for key in sorted(self.candidates)]
        print("\nDetected chairs")
        if not candidates:
            print("  waiting for /colt/bridle candidates...")
            return
        for item in candidates:
            print(
                "  {id:12s} p={confidence:.2f} "
                "xyz=({x:.2f}, {y:.2f}, {z:.2f})".format(**item)
            )

    def prompt_loop(self):
        rate = rospy.Rate(2)
        while not rospy.is_shutdown() and not self.chair_ids():
            rate.sleep()

        while not rospy.is_shutdown():
            self.print_candidates()
            print(
                "\nCurrent selection: source={} target={}".format(
                    self.source_chair or "<none>",
                    self.target_chair or "<none>",
                )
            )
            print("Commands: s <chair_id>, t <chair_id>, clear, r, q")
            try:
                command = input("> ").strip()
            except EOFError:
                rospy.loginfo("stdin closed; keeping current latched selections alive")
                rospy.spin()
                return

            if command == "q":
                rospy.signal_shutdown("operator requested quit")
                return
            if command == "r":
                continue
            if command == "clear":
                self.source_chair = ""
                self.target_chair = ""
                self.source_pub.publish(String(data=""))
                self.target_pub.publish(String(data=""))
                rospy.loginfo("Cleared chair selections")
                continue

            parts = command.split()
            if len(parts) != 2 or parts[0] not in {"s", "t"}:
                print("Invalid command")
                continue
            chair_id = parts[1]
            if chair_id not in self.chair_ids():
                print(f"Unknown chair id: {chair_id}")
                continue
            if parts[0] == "s":
                self.source_chair = chair_id
            else:
                self.target_chair = chair_id
            self.publish_current()

    def spin(self):
        rospy.sleep(0.5)
        self.publish_current()
        if self.prompt:
            self.prompt_loop()
        else:
            rospy.loginfo("Prompt disabled; keeping latched chair selections alive")
            rospy.spin()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="")
    parser.add_argument("--target", default="")
    parser.add_argument("--no-prompt", action="store_true")
    args, _ = parser.parse_known_args()

    rospy.init_node("colt_terminal_chair_selector")
    if args.no_prompt:
        rospy.set_param("~prompt", False)
    TerminalChairSelector(source_chair=args.source, target_chair=args.target).spin()


if __name__ == "__main__":
    main()
