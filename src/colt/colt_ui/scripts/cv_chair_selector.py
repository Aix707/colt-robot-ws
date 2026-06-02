#!/usr/bin/env python3
"""OpenCV chair selector for Colt detections."""

import os
import threading
from dataclasses import dataclass

import cv2
import numpy as np
import rospy
from colt_msgs.msg import Detection3D, Detection3DArray
from sensor_msgs.msg import Image
from std_msgs.msg import String, UInt8


PT_STATE_SOURCE = 0
PT_STATE_TARGET = 1
STATE_TEXT = {
    Detection3D.STATE_LOST: "lost",
    Detection3D.STATE_VISIBLE: "visible",
    Detection3D.STATE_VISIBLE_NO_DEPTH: "no_depth",
}


@dataclass(frozen=True)
class UiObject:
    object_id: str
    parent_id: str
    object_type: str
    role: str
    state: int
    confidence: float
    frame_id: str
    x: float
    y: float
    z: float
    bbox: tuple

    @property
    def selectable(self):
        x1, y1, x2, y2 = self.bbox
        return (
            self.object_type == "chair"
            and self.state == Detection3D.STATE_VISIBLE
            and x2 > x1
            and y2 > y1
        )

    def contains(self, x, y):
        x1, y1, x2, y2 = self.bbox
        return x1 <= x <= x2 and y1 <= y <= y2

    def center_distance_sq(self, x, y):
        x1, y1, x2, y2 = self.bbox
        cx = 0.5 * (x1 + x2)
        cy = 0.5 * (y1 + y2)
        return (cx - x) ** 2 + (cy - y) ** 2


class CvChairSelector:
    def __init__(self):
        self.window_name = rospy.get_param("~window_name", "Colt Chair Selector")
        self.input_topic = rospy.get_param("~input_topic", "/colt/bridle/detections")
        self.image_topic = rospy.get_param("~image_topic", "/colt/bridle/debug_image")
        self.source = rospy.get_param("~source_chair", "").strip()
        self.target = rospy.get_param("~target_chair", "").strip()
        self.lost_hide_after_sec = float(rospy.get_param("~lost_hide_after_sec", 2.0))
        self.pt_state = PT_STATE_SOURCE
        self.candidate = ""
        self.latest_image = None
        self.objects = {}
        self.chairs = {}
        self.lost_since = {}
        self.camera_height = 0
        self.lock = threading.Lock()

        if not os.environ.get("DISPLAY"):
            rospy.logerr("DISPLAY is not set; OpenCV selector cannot open a window")
            rospy.signal_shutdown("missing DISPLAY")
            return

        self.source_pub = rospy.Publisher("/colt/ui/selected_source_chair", String, queue_size=1, latch=True)
        self.target_pub = rospy.Publisher("/colt/ui/selected_target_chair", String, queue_size=1, latch=True)
        self.pt_state_pub = rospy.Publisher("/colt/ui/pt_state", UInt8, queue_size=1, latch=True)
        rospy.Subscriber(self.input_topic, Detection3DArray, self.detections_cb, queue_size=1)
        rospy.Subscriber(self.image_topic, Image, self.image_cb, queue_size=1)

        cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
        cv2.setMouseCallback(self.window_name, self.mouse_cb)
        rospy.on_shutdown(self.close)
        self.publish_selection()

    def detections_cb(self, msg):
        objects = {}
        chairs = {}
        lost_since = dict(self.lost_since)
        now = rospy.Time.now().to_sec()
        seen_ids = set()
        for detection in msg.detections:
            item = UiObject(
                object_id=detection.id,
                parent_id=detection.parent_id,
                object_type=detection.object_type,
                role=detection.role,
                state=int(detection.state),
                confidence=float(detection.confidence),
                frame_id=detection.header.frame_id,
                x=float(detection.x),
                y=float(detection.y),
                z=float(detection.z),
                bbox=(
                    int(detection.bbox.xmin),
                    int(detection.bbox.ymin),
                    int(detection.bbox.xmax),
                    int(detection.bbox.ymax),
                ),
            )
            seen_ids.add(item.object_id)
            if item.state == Detection3D.STATE_LOST:
                lost_since.setdefault(item.object_id, now)
            else:
                lost_since.pop(item.object_id, None)
            objects[item.object_id] = item
            if item.object_type == "chair":
                chairs[item.object_id] = item
        for object_id in list(lost_since):
            if object_id not in seen_ids:
                lost_since.pop(object_id, None)
        with self.lock:
            self.objects = objects
            self.chairs = chairs
            self.lost_since = lost_since
            if self.candidate and self.candidate not in chairs:
                self.candidate = ""
            elif self.candidate:
                chair = chairs.get(self.candidate)
                if chair is not None and self.should_hide_lost(chair, lost_since, now):
                    self.candidate = ""

    def image_cb(self, msg):
        try:
            image = self.image_to_bgr8(msg)
        except Exception as exc:
            rospy.logwarn_throttle(5.0, "Selector image conversion failed: %s", exc)
            return
        with self.lock:
            self.latest_image = image

    def image_to_bgr8(self, msg):
        if msg.encoding == "bgr8":
            array = np.frombuffer(msg.data, dtype=np.uint8).reshape(msg.height, msg.step)
            return np.ascontiguousarray(array[:, : msg.width * 3].reshape(msg.height, msg.width, 3))
        if msg.encoding == "rgb8":
            array = np.frombuffer(msg.data, dtype=np.uint8).reshape(msg.height, msg.step)
            rgb = np.ascontiguousarray(array[:, : msg.width * 3].reshape(msg.height, msg.width, 3))
            return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        raise ValueError(f"unsupported image encoding: {msg.encoding}")

    def mouse_cb(self, event, x, y, _flags, _param):
        if event != cv2.EVENT_LBUTTONDOWN:
            return
        with self.lock:
            if self.camera_height and y >= self.camera_height:
                return
            chairs = list(self.chairs.values())
        selectable = [chair for chair in chairs if chair.selectable]
        inside = [chair for chair in selectable if chair.contains(x, y)]
        if inside:
            chosen = max(inside, key=lambda item: item.confidence)
        elif selectable:
            chosen = min(selectable, key=lambda item: item.center_distance_sq(x, y))
            if chosen.center_distance_sq(x, y) > 3600.0:
                return
        else:
            return
        with self.lock:
            self.candidate = chosen.object_id
        rospy.loginfo("Candidate chair: %s", chosen.object_id)

    def publish_selection(self):
        if self.source and self.source == self.target:
            rospy.logwarn("Source and target cannot be the same chair")
            return
        self.source_pub.publish(String(data=self.source))
        self.target_pub.publish(String(data=self.target))
        self.pt_state_pub.publish(UInt8(data=self.pt_state))
        rospy.loginfo(
            "UI selection: source=%s target=%s pt_state=%d",
            self.source or "<none>",
            self.target or "<none>",
            self.pt_state,
        )

    def assign_candidate(self, role):
        with self.lock:
            candidate = self.candidate
            chair = self.chairs.get(candidate)
        if chair is None or not chair.selectable:
            rospy.logwarn("No visible chair candidate selected")
            return
        if role == "source":
            if candidate == self.target:
                rospy.logwarn("Source and target cannot be the same chair")
                return
            self.source = candidate
        else:
            if candidate == self.source:
                rospy.logwarn("Source and target cannot be the same chair")
                return
            self.target = candidate
        self.pt_state = PT_STATE_TARGET if role == "target" else PT_STATE_SOURCE
        self.publish_selection()

    def clear(self):
        self.source = ""
        self.target = ""
        self.pt_state = PT_STATE_SOURCE
        with self.lock:
            self.candidate = ""
        self.publish_selection()

    def toggle_target_state(self):
        if not self.source or not self.target:
            rospy.logwarn("Select both source and target before switching pt_state")
            return
        self.pt_state = PT_STATE_TARGET if self.pt_state == PT_STATE_SOURCE else PT_STATE_SOURCE
        self.publish_selection()

    def render(self):
        with self.lock:
            image = None if self.latest_image is None else self.latest_image.copy()
            objects = dict(self.objects)
            chairs = dict(self.chairs)
            lost_since = dict(self.lost_since)
            candidate = self.candidate
        if image is None:
            image = np.zeros((540, 960, 3), dtype=np.uint8)
            cv2.putText(image, "waiting for image", (24, 52), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 2, cv2.LINE_AA)
        with self.lock:
            self.camera_height = image.shape[0]
        now = rospy.Time.now().to_sec()
        for chair in sorted(chairs.values(), key=lambda item: item.object_id):
            if self.should_hide_lost(chair, lost_since, now):
                continue
            self.draw_chair(image, chair, candidate)
        self.draw_status(image, candidate)
        cv2.imshow(self.window_name, self.add_coordinate_panel(image, objects))
        self.handle_key(cv2.waitKey(1) & 0xFF)

    def should_hide_lost(self, item, lost_since, now):
        if item.state != Detection3D.STATE_LOST:
            return False
        if self.lost_hide_after_sec < 0.0:
            return False
        since = lost_since.get(item.object_id)
        return since is not None and (float(now) - float(since)) >= self.lost_hide_after_sec

    def draw_chair(self, image, chair, candidate):
        x1, y1, x2, y2 = chair.bbox
        color = (120, 120, 120)
        if chair.object_id == self.source:
            color = (0, 220, 0)
        elif chair.object_id == self.target:
            color = (255, 160, 0)
        elif chair.object_id == candidate:
            color = (0, 255, 255)
        if chair.state == Detection3D.STATE_LOST:
            color = (80, 80, 80)
        cv2.rectangle(image, (x1, y1), (x2, y2), color, 2)
        label = f"{chair.object_id} {STATE_TEXT.get(chair.state, chair.state)} {chair.confidence:.2f}"
        cv2.putText(image, label, (x1, max(18, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2, cv2.LINE_AA)

    def draw_status(self, image, candidate):
        overlay = image.copy()
        cv2.rectangle(overlay, (0, 0), (image.shape[1], 72), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.55, image, 0.45, 0.0, image)
        state_name = "target" if self.pt_state == PT_STATE_TARGET else "source"
        lines = [
            f"candidate={candidate or '<none>'}  source={self.source or '<none>'}  target={self.target or '<none>'}  pt={state_name}",
            "mouse: candidate   s: source   t: target   w: switch pt   c: clear   q: quit",
        ]
        for index, line in enumerate(lines):
            cv2.putText(image, line, (12, 26 + index * 30), cv2.FONT_HERSHEY_SIMPLEX, 0.68, (255, 255, 255), 2, cv2.LINE_AA)

    def add_coordinate_panel(self, image, objects):
        width = image.shape[1]
        panel_height = 154
        panel = np.full((panel_height, width, 3), (24, 28, 32), dtype=np.uint8)
        cv2.line(panel, (0, 0), (width, 0), (90, 90, 90), 1)

        rows = self.coordinate_rows(objects)
        frame_id = self.common_frame_id([item for _label, item in rows if item is not None])
        frame_text = f"coordinates x/y/z in meters   frame={frame_id or '<none>'}"
        cv2.putText(panel, frame_text, (12, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (220, 220, 220), 1, cv2.LINE_AA)

        for index, (label, item) in enumerate(rows):
            y = 50 + index * 21
            color = (180, 180, 180) if item is None or item.state == Detection3D.STATE_LOST else (235, 235, 235)
            cv2.putText(panel, self.coordinate_line(label, item), (12, y), cv2.FONT_HERSHEY_SIMPLEX, 0.48, color, 1, cv2.LINE_AA)
        return np.vstack((image, panel))

    def coordinate_rows(self, objects):
        source_chair = objects.get(self.source) if self.source else None
        target_chair = objects.get(self.target) if self.target else None
        source_seat = self.child_object(objects, self.source, "seat") if self.source else None
        target_seat = self.child_object(objects, self.target, "seat") if self.target else None
        aluminum = self.child_object(objects, source_seat.object_id, "item") if source_seat is not None else None
        if aluminum is None:
            aluminum = self.role_object(objects, "item", "source")
        return [
            ("SRC CHAIR", source_chair),
            ("SRC SEAT ", source_seat),
            ("ALUMINUM ", aluminum),
            ("TGT CHAIR", target_chair),
            ("TGT SEAT ", target_seat),
        ]

    def child_object(self, objects, parent_id, object_type):
        matches = [
            item
            for item in objects.values()
            if item.parent_id == parent_id and item.object_type == object_type
        ]
        return self.best_object(matches)

    def role_object(self, objects, object_type, role):
        matches = [
            item
            for item in objects.values()
            if item.object_type == object_type and item.role == role
        ]
        return self.best_object(matches)

    def best_object(self, matches):
        if not matches:
            return None
        return sorted(matches, key=lambda item: (item.state == Detection3D.STATE_LOST, item.object_id))[0]

    def common_frame_id(self, items):
        frames = sorted({item.frame_id for item in items if item.frame_id})
        if not frames:
            return ""
        if len(frames) == 1:
            return frames[0]
        return "mixed"

    def coordinate_line(self, label, item):
        if item is None:
            return f"{label}  <none>"
        state = STATE_TEXT.get(item.state, str(item.state))
        return (
            f"{label}  {item.object_id:<20} {state:<8} "
            f"x={item.x:+.3f} y={item.y:+.3f} z={item.z:+.3f} c={item.confidence:.2f}"
        )

    def handle_key(self, key):
        if key in (255, 0xFF):
            return
        if key == ord("s"):
            self.assign_candidate("source")
        elif key == ord("t"):
            self.assign_candidate("target")
        elif key == ord("w"):
            self.toggle_target_state()
        elif key == ord("c"):
            self.clear()
        elif key in (ord("q"), 27):
            rospy.signal_shutdown("operator closed selector")

    def spin(self):
        rate = rospy.Rate(30)
        while not rospy.is_shutdown():
            self.render()
            rate.sleep()

    def close(self):
        try:
            cv2.destroyWindow(self.window_name)
        except Exception:
            pass


def main():
    rospy.init_node("colt_cv_chair_selector")
    selector = CvChairSelector()
    if not rospy.is_shutdown():
        selector.spin()


if __name__ == "__main__":
    main()
