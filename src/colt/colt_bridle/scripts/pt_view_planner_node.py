#!/usr/bin/env python3
"""Publish pan-tilt observation goal points without commanding the pan-tilt unit."""

import rospy
from colt_msgs.msg import Detection3DArray, PerceptionState
from geometry_msgs.msg import Point, PoseStamped, Quaternion


class PtViewPlanner:
    def __init__(self):
        self.state = PerceptionState()
        self.goal_pub = rospy.Publisher("/colt/bridle/pt_view_goal", PoseStamped, queue_size=10)
        rospy.Subscriber("/colt/bridle/detections", Detection3DArray, self.detections_cb)
        rospy.Subscriber("/colt/bridle/perception_state", PerceptionState, self.state_cb)

    def state_cb(self, msg):
        self.state = msg

    def score_detection(self, detection):
        # 按当前任务价值排序：可抓取小铝块最高，其次源椅面、目标椅面和椅子。
        if detection.role == "aluminum_block" and self.state.ready_for_grasp:
            return 100
        if detection.role == "source_seat":
            return 80
        if detection.role == "target_seat" and self.state.ready_for_place:
            return 70
        if detection.role in {"source_chair", "target_chair"}:
            return 50
        if detection.class_name == "chair":
            return 20
        return 0

    def detections_cb(self, msg):
        if not msg.detections:
            return
        best = max(msg.detections, key=self.score_detection)
        if self.score_detection(best) <= 0:
            return
        # 这里只发布观察空间点；真正云台角度由后续限幅转发器计算。
        goal = PoseStamped()
        goal.header = msg.header
        goal.pose.position = Point(
            x=best.pose.pose.position.x,
            y=best.pose.pose.position.y,
            z=best.pose.pose.position.z,
        )
        if best.class_name == "aluminum_block":
            goal.pose.position.z += 0.05
        goal.pose.orientation = Quaternion(x=0.0, y=0.0, z=0.0, w=1.0)
        self.goal_pub.publish(goal)


def main():
    rospy.init_node("colt_pt_view_planner")
    PtViewPlanner()
    rospy.loginfo("Colt pan-tilt view planner publishing /colt/bridle/pt_view_goal")
    rospy.spin()


if __name__ == "__main__":
    main()
