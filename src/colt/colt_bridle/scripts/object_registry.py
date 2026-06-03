#!/usr/bin/env python3
"""Stable Colt object state helpers."""

import math
from dataclasses import dataclass, replace
from typing import Dict, Optional, Tuple

import rospy
from colt_msgs.msg import Detection3D


@dataclass(frozen=True)
class ObjectState:
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
    bbox: Optional[Tuple[int, int, int, int]] = None
    stamp: object = None


def to_detection_message(obj):
    message = Detection3D()
    message.header.stamp = obj.stamp
    message.header.frame_id = obj.frame_id
    message.id = obj.object_id
    message.parent_id = obj.parent_id
    message.object_type = obj.object_type
    message.role = obj.role
    message.state = int(obj.state)
    message.confidence = float(obj.confidence)
    message.x = float(obj.x)
    message.y = float(obj.y)
    message.z = float(obj.z)
    if obj.bbox is not None:
        x1, y1, x2, y2 = obj.bbox
        message.bbox.xmin = int(x1)
        message.bbox.ymin = int(y1)
        message.bbox.xmax = int(x2)
        message.bbox.ymax = int(y2)
    return message


def object_role(object_id, selection):
    if object_id and object_id == selection.get("source", ""):
        return "source"
    if object_id and object_id == selection.get("target", ""):
        return "target"
    return "normal"


def bbox_iou(lhs, rhs):
    if lhs is None or rhs is None:
        return 0.0
    lx1, ly1, lx2, ly2 = lhs
    rx1, ry1, rx2, ry2 = rhs
    inter_x1 = max(lx1, rx1)
    inter_y1 = max(ly1, ry1)
    inter_x2 = min(lx2, rx2)
    inter_y2 = min(ly2, ry2)
    if inter_x2 <= inter_x1 or inter_y2 <= inter_y1:
        return 0.0
    inter = float(inter_x2 - inter_x1) * float(inter_y2 - inter_y1)
    lhs_area = float(max(0, lx2 - lx1)) * float(max(0, ly2 - ly1))
    rhs_area = float(max(0, rx2 - rx1)) * float(max(0, ry2 - ry1))
    union = lhs_area + rhs_area - inter
    return inter / union if union > 0.0 else 0.0


def distance_sq(lhs, rhs):
    return (
        (float(lhs.x) - float(rhs["x"])) ** 2
        + (float(lhs.y) - float(rhs["y"])) ** 2
        + (float(lhs.z) - float(rhs["z"])) ** 2
    )


def distance_m(lhs, rhs):
    return math.sqrt(distance_sq(lhs, rhs))


def shift_position(position, delta):
    return (
        float(position[0]) + float(delta[0]),
        float(position[1]) + float(delta[1]),
        float(position[2]) + float(delta[2]),
    )


def object_position(obj):
    return (float(obj.x), float(obj.y), float(obj.z))


class ChairRegistry:
    def __init__(
        self,
        max_match_distance,
        selected_reacquire_distance_m=0.6,
        selected_reacquire_margin_m=0.30,
        selected_reacquire_iou=0.01,
        chair_smooth_alpha=0.35,
        chair_jump_reject_m=0.6,
    ):
        self.max_match_distance_sq = float(max_match_distance) ** 2
        self.selected_reacquire_distance_m = float(selected_reacquire_distance_m)
        self.selected_reacquire_margin_m = float(selected_reacquire_margin_m)
        self.selected_reacquire_iou = float(selected_reacquire_iou)
        self.chair_smooth_alpha = min(max(float(chair_smooth_alpha), 0.0), 1.0)
        self.chair_jump_reject_m = float(chair_jump_reject_m)
        self.next_chair_index = 0
        self.chairs: Dict[str, ObjectState] = {}

    def update(self, observations, selection, stamp):
        selected_roles = self._selected_roles(selection)
        reacquired_pairs = self._selected_reacquire_pairs(observations, selected_roles)
        reacquired_pairs += self._normal_reacquire_pairs(observations, selection, reacquired_pairs)
        pairs = reacquired_pairs + self._match_pairs(observations, reacquired_pairs)
        assigned_indices = set()
        active_ids = {chair_id for chair_id, _ in pairs}

        for chair_id, index in pairs:
            assigned_indices.add(index)
            self._update_existing(chair_id, observations[index], selection, stamp)

        for index, observation in enumerate(observations):
            if index in assigned_indices:
                continue
            created = self._create_new(observation, selection, stamp)
            if created is not None:
                active_ids.add(created.object_id)

        for chair_id, current in list(self.chairs.items()):
            if chair_id in active_ids:
                continue
            self.chairs[chair_id] = replace(
                current,
                role=object_role(chair_id, selection),
                state=Detection3D.STATE_LOST,
                confidence=0.0,
                stamp=stamp,
            )

        all_objects = sorted(self.chairs.values(), key=lambda item: item.object_id)
        return all_objects, dict(self.chairs)

    def _selected_roles(self, selection):
        roles = []
        for role in ("source", "target"):
            chair_id = selection.get(role, "")
            if chair_id:
                roles.append((role, chair_id))
        return roles

    def _selected_reacquire_pairs(self, observations, selected_roles):
        pairs = []
        assigned_indices = set()
        for role, chair_id in selected_roles:
            current = self.chairs.get(chair_id)
            if current is None or int(current.state) != Detection3D.STATE_LOST:
                continue
            candidate = self._reacquire_candidate(role, current, observations, assigned_indices)
            if candidate is None:
                continue
            index, distance, iou = candidate
            assigned_indices.add(index)
            pairs.append((chair_id, index))
            distance_text = "unknown" if distance is None else f"{distance:.2f}m"
            rospy.loginfo(
                "Chair registry: %s %s rebound to detection[%d] distance=%s iou=%.3f",
                role,
                chair_id,
                index,
                distance_text,
                iou,
            )
        return pairs

    def _normal_reacquire_pairs(self, observations, selection, reserved_pairs):
        selected_ids = {chair_id for _role, chair_id in self._selected_roles(selection)}
        assigned_indices = {index for _chair_id, index in reserved_pairs}
        pairs = []
        for chair_id, current in sorted(self.chairs.items()):
            if chair_id in selected_ids or int(current.state) != Detection3D.STATE_LOST:
                continue
            candidate = self._reacquire_candidate("normal", current, observations, assigned_indices)
            if candidate is None:
                continue
            index, distance, iou = candidate
            assigned_indices.add(index)
            pairs.append((chair_id, index))
            distance_text = "unknown" if distance is None else f"{distance:.2f}m"
            rospy.loginfo(
                "Chair registry: normal %s rebound to detection[%d] distance=%s iou=%.3f",
                chair_id,
                index,
                distance_text,
                iou,
            )
        return pairs

    def _reacquire_candidate(self, role, current, observations, assigned_indices):
        candidates = []
        rejected_by_distance = []
        for index, observation in enumerate(observations):
            if index in assigned_indices:
                continue
            state = int(observation["state"])
            if state == Detection3D.STATE_LOST:
                continue
            iou = bbox_iou(current.bbox, observation["bbox"])
            if state == Detection3D.STATE_VISIBLE:
                distance = distance_m(current, observation)
                if distance > self.selected_reacquire_distance_m:
                    rejected_by_distance.append((distance, index, iou))
                    continue
                candidates.append((distance, -iou, index, iou))
            elif iou >= self.selected_reacquire_iou:
                candidates.append((float("inf"), -iou, index, iou))

        if not candidates:
            if rejected_by_distance:
                distance, index, iou = min(rejected_by_distance, key=lambda item: item[0])
                rospy.logwarn_throttle(
                    2.0,
                    "Chair registry: reject %s %s rebound to detection[%d], distance %.2fm > %.2fm iou=%.3f",
                    role,
                    current.object_id,
                    index,
                    distance,
                    self.selected_reacquire_distance_m,
                    iou,
                )
            else:
                rospy.logwarn_throttle(
                    2.0,
                    "Chair registry: cannot rebound %s %s, no qualifying visible chair candidates",
                    role,
                    current.object_id,
                )
            return None

        candidates.sort(key=lambda item: (item[0], item[1]))
        best = candidates[0]
        if len(candidates) > 1:
            second = candidates[1]
            if not math.isfinite(best[0]) or not math.isfinite(second[0]) or second[0] - best[0] < self.selected_reacquire_margin_m:
                rospy.logwarn_throttle(
                    2.0,
                    "Chair registry: reject %s %s rebound, ambiguous candidates detection[%d] and detection[%d]",
                    role,
                    current.object_id,
                    best[2],
                    second[2],
                )
                return None
        distance = None if not math.isfinite(best[0]) else best[0]
        return best[2], distance, best[3]

    def _match_pairs(self, observations, reserved_pairs):
        reserved_ids = {chair_id for chair_id, _index in reserved_pairs}
        reserved_indices = {index for _chair_id, index in reserved_pairs}
        candidates = []
        for chair_id, current in self.chairs.items():
            if chair_id in reserved_ids:
                continue
            if int(current.state) == Detection3D.STATE_LOST:
                continue
            for index, observation in enumerate(observations):
                if index in reserved_indices:
                    continue
                score = self._match_score(current, observation)
                if score is not None:
                    candidates.append((score, chair_id, index))
        candidates.sort(key=lambda item: item[0])

        assigned_ids = set()
        assigned_indices = set()
        matches = []
        for _score, chair_id, index in candidates:
            if chair_id in assigned_ids or index in assigned_indices:
                continue
            assigned_ids.add(chair_id)
            assigned_indices.add(index)
            matches.append((chair_id, index))
        return matches

    def _match_score(self, current, observation):
        if observation["state"] == Detection3D.STATE_VISIBLE:
            score = distance_sq(current, observation)
            if score <= self.max_match_distance_sq:
                return (0, score)
        iou = bbox_iou(current.bbox, observation["bbox"])
        if iou > 0.05:
            return (1, -iou)
        return None

    def _update_existing(self, chair_id, observation, selection, stamp):
        current = self.chairs[chair_id]
        if int(observation["state"]) == Detection3D.STATE_VISIBLE:
            updated = self._chair_object(
                chair_id,
                observation,
                selection,
                stamp,
                position=self._smoothed_visible_position(current, observation),
            )
        else:
            updated = self._chair_object(
                chair_id,
                observation,
                selection,
                stamp,
                position=object_position(current),
                frame_id=current.frame_id,
            )
        self.chairs[chair_id] = updated
        return updated

    def _smoothed_visible_position(self, current, observation):
        distance = distance_m(current, observation)
        if distance > self.chair_jump_reject_m:
            rospy.logwarn_throttle(
                2.0,
                "Chair registry: reject %s world jump %.2fm > %.2fm",
                current.object_id,
                distance,
                self.chair_jump_reject_m,
            )
            return object_position(current)
        alpha = self.chair_smooth_alpha
        return (
            float(current.x) * (1.0 - alpha) + float(observation["x"]) * alpha,
            float(current.y) * (1.0 - alpha) + float(observation["y"]) * alpha,
            float(current.z) * (1.0 - alpha) + float(observation["z"]) * alpha,
        )

    def _create_new(self, observation, selection, stamp):
        if int(observation["state"]) != Detection3D.STATE_VISIBLE:
            return None
        chair_id = f"chair_{self.next_chair_index}"
        self.next_chair_index += 1
        created = self._chair_object(chair_id, observation, selection, stamp)
        self.chairs[chair_id] = created
        return created

    def _chair_object(self, chair_id, observation, selection, stamp, position=None, frame_id=None):
        if position is None:
            position = (observation["x"], observation["y"], observation["z"])
        return ObjectState(
            object_id=chair_id,
            parent_id="",
            object_type="chair",
            role=object_role(chair_id, selection),
            state=int(observation["state"]),
            confidence=float(observation["confidence"]),
            frame_id=frame_id or observation["frame_id"],
            x=float(position[0]),
            y=float(position[1]),
            z=float(position[2]),
            bbox=observation["bbox"],
            stamp=stamp,
        )


def child_object(parent_id, object_type, role, state, confidence, frame_id, position, bbox, stamp):
    object_id = f"{parent_id}_{object_type}"
    return ObjectState(
        object_id=object_id,
        parent_id=parent_id,
        object_type=object_type,
        role=role,
        state=int(state),
        confidence=float(confidence),
        frame_id=frame_id,
        x=float(position[0]),
        y=float(position[1]),
        z=float(position[2]),
        bbox=bbox,
        stamp=stamp,
    )
