#!/usr/bin/env python3
"""Terminal selector for visible chair detections."""

import argparse
import select
import sys
import termios
import threading
import tty
from dataclasses import dataclass
from functools import partial
from typing import Optional

import rospy
from colt_msgs.msg import Detection3D, Detection3DArray
from std_msgs.msg import String, UInt8


ROLES = ("source", "target")
ROLE_COMMANDS = {"s": "source", "t": "target"}
PT_STATE_SOURCE = 0
PT_STATE_TARGET = 1
STATE_NAMES = {
    Detection3D.STATE_LOST: "lost",
    Detection3D.STATE_VISIBLE: "visible",
    Detection3D.STATE_VISIBLE_NO_DEPTH: "visible_no_depth",
}


@dataclass(frozen=True)
class ChairItem:
    chair_id: str
    state: int
    frame_id: str
    confidence: float
    seen_age: Optional[float]
    x: float
    y: float
    z: float

    @classmethod
    def from_detection(cls, detection, default_frame, now):
        stamp = detection.header.stamp
        seen_age = None if stamp == rospy.Time(0) else max(0.0, (now - stamp).to_sec())
        return cls(
            chair_id=detection.id,
            state=int(detection.state),
            frame_id=detection.header.frame_id or default_frame,
            confidence=float(detection.confidence),
            seen_age=seen_age,
            x=float(detection.x),
            y=float(detection.y),
            z=float(detection.z),
        )

    @property
    def selectable(self):
        return self.state == Detection3D.STATE_VISIBLE

    @property
    def state_text(self):
        return STATE_NAMES.get(self.state, str(self.state))

    @property
    def age_text(self):
        return "--" if self.seen_age is None else f"{self.seen_age:.1f}s"

    def row(self, index):
        return (
            "  {idx:<2d} {chair_id:15s} {state:16s} {confidence:10.2f}  {age:>6s}  "
            "({x:.2f},{y:.2f},{z:.2f}) {frame_id}"
        ).format(idx=index, age=self.age_text, state=self.state_text, **self.__dict__)


@dataclass
class Selection:
    source: str = ""
    target: str = ""

    def get(self, role):
        return getattr(self, role)

    def set(self, role, chair_id):
        setattr(self, role, chair_id)

    def clear(self, role):
        self.set(role, "")

    def clear_all(self):
        for role in ROLES:
            self.clear(role)

    @property
    def invalid(self):
        return self.source and self.source == self.target


class TerminalChairSelector:
    def __init__(self, source_chair="", target_chair=""):
        self.lock = threading.Lock()
        self.chairs = {}
        self.input_topic = rospy.get_param("~input_topic", "/colt/bridle/detections")
        self.prompt = bool(rospy.get_param("~prompt", True)) and sys.stdin.isatty()
        self.selection = Selection(
            source=source_chair.strip() or rospy.get_param("~source_chair", "").strip(),
            target=target_chair.strip() or rospy.get_param("~target_chair", "").strip(),
        )
        self.pt_state = PT_STATE_SOURCE
        self.publishers = {
            role: rospy.Publisher(
                f"/colt/ui/selected_{role}_chair", String, queue_size=1, latch=True
            )
            for role in ROLES
        }
        self.pt_state_pub = rospy.Publisher("/colt/ui/pt_state", UInt8, queue_size=1, latch=True)
        self.command_handlers = self._build_command_handlers()
        rospy.Subscriber(self.input_topic, Detection3DArray, self.detections_cb, queue_size=10)

    # 1. 接收物体状态
    def detections_cb(self, msg):
        now = rospy.Time.now()
        chairs = {
            detection.id: ChairItem.from_detection(detection, msg.header.frame_id, now)
            for detection in msg.detections
            if detection.object_type == "chair"
        }
        with self.lock:
            self.chairs = chairs

    def visible_chairs(self):
        with self.lock:
            return [self.chairs[key] for key in sorted(self.chairs)]

    def chair_by_id(self, chair_id):
        with self.lock:
            return self.chairs.get(chair_id)

    def wait_until_visible(self):
        wait_rate = rospy.Rate(2)
        while not rospy.is_shutdown() and not self.visible_chairs():
            wait_rate.sleep()

    def publish_selection(self):
        if self.selection.invalid:
            rospy.logwarn("Source and target cannot be the same chair: %s", self.selection.source)
            return False
        for role in ROLES:
            self.publishers[role].publish(String(data=self.selection.get(role)))
        self.pt_state_pub.publish(UInt8(data=self.pt_state))
        rospy.loginfo(
            "Selected visible chairs: source=%s target=%s pt_state=%d",
            self.selection.source or "<none>",
            self.selection.target or "<none>",
            self.pt_state,
        )
        return True

    # 2. 显示需要的项目
    def selection_label(self, role):
        chair_id = self.selection.get(role)
        if not chair_id:
            return "<none>"
        return chair_id if self.chair_by_id(chair_id) else f"{chair_id} (not visible)"

    def print_status(self):
        print(
            "\nCurrent selection: source={} target={} pt_state={}".format(
                self.selection_label("source"),
                self.selection_label("target"),
                self.pt_state,
            )
        )
        print("Only chairs with state=visible can be newly selected.")
        print("Choose chairs -> pt_state resets to 0 and PT faces source. swap -> pt_state becomes 1 and PT faces target.")

    def print_candidates(self):
        chairs = self.visible_chairs()
        print("\nVisible chairs")
        if not chairs:
            print("  waiting for /colt/bridle/detections ...")
            return
        print("  #  ID              state            confidence  age      xyz")
        for index, chair in enumerate(chairs):
            print(chair.row(index))

    # 3. 选择并贴标签
    def resolve_token(self, token, chairs):
        if token.isdigit():
            index = int(token)
            return chairs[index].chair_id if 0 <= index < len(chairs) else ""
        return token if token in {chair.chair_id for chair in chairs} else ""

    def validate_choice(self, role, chair_id):
        chair = self.chair_by_id(chair_id)
        if chair is None:
            return f"Unknown visible chair id: {chair_id}"
        if not chair.selectable:
            return f"Chair {chair_id} state={chair.state_text} is not selectable"
        other_role = "target" if role == "source" else "source"
        if chair_id == self.selection.get(other_role):
            return "Source and target cannot be the same chair"
        return ""

    def choose(self, role, token):
        chairs = self.visible_chairs()
        chair_id = self.resolve_token(token, chairs)
        if not chair_id:
            return f"Unknown chair index/id: {token}"
        error = self.validate_choice(role, chair_id)
        if error:
            return error
        self.selection.set(role, chair_id)
        self.pt_state = PT_STATE_SOURCE
        self.publish_selection()
        return ""

    def clear(self, role):
        if role == "all":
            self.selection.clear_all()
        elif role in ROLES:
            self.selection.clear(role)
        else:
            return "Use: clear source | clear target | clear all"
        self.pt_state = PT_STATE_SOURCE
        self.publish_selection()
        return ""

    def swap(self):
        if not self.selection.source or not self.selection.target:
            return "Swap requires both source and target chairs"
        self.pt_state = PT_STATE_TARGET
        self.publish_selection()
        return ""

    def quit(self):
        rospy.signal_shutdown("operator requested quit")
        return ""

    def _build_command_handlers(self):
        handlers = {
            "clear": self.clear,
            "swap": lambda: self.swap(),
            "q": lambda: self.quit(),
        }
        handlers.update(
            {command: partial(self.choose, role) for command, role in ROLE_COMMANDS.items()}
        )
        return handlers

    def handle_command(self, command):
        if not command:
            return ""
        verb, _, arg = command.partition(" ")
        handler = self.command_handlers.get(verb)
        if handler is None:
            return "Invalid command"
        return handler(arg.strip()) if arg else handler()

    def prompt_loop(self):
        self.wait_until_visible()
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        input_buffer = []
        last_message = ""

        try:
            tty.setcbreak(fd)
            rate = rospy.Rate(5)  # 5Hz 的自动刷新率
            while not rospy.is_shutdown():
                # 无阻塞读取所有敲击的字符
                while sys.stdin in select.select([sys.stdin], [], [], 0.0)[0]:
                    ch = sys.stdin.read(1)
                    if ch in ('\n', '\r'):
                        command = "".join(input_buffer).strip()
                        input_buffer.clear()
                        if command:
                            last_message = self.handle_command(command)
                    elif ch in ('\x7f', '\x08'):  # 处理退格键 (Backspace)
                        if input_buffer:
                            input_buffer.pop()
                    elif ch == '\x03':  # Ctrl+C
                        rospy.signal_shutdown("Ctrl+C")
                        return
                    else:
                        input_buffer.append(ch)

                # 使用 ANSI 转义码刷新屏幕，不留残影
                sys.stdout.write("\033[2J\033[H")
                self.print_status()
                self.print_candidates()

                if last_message:
                    print(f"\n[Result]: {last_message}")

                print("\nCommands: s <#|id>, t <#|id>, swap(target), clear source|target|all, q")
                sys.stdout.write("> " + "".join(input_buffer))
                sys.stdout.flush()

                rate.sleep()
        except Exception as e:
            rospy.logerr(f"Terminal UI error: {e}")
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    def spin(self):
        rospy.sleep(0.5)
        self.publish_selection()
        if self.prompt:
            self.prompt_loop()
        else:
            rospy.loginfo("Prompt disabled; keeping current latched chair selections alive")
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
