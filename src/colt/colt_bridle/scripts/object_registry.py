#!/usr/bin/env python3
"""Stable Colt object state helpers."""

from dataclasses import dataclass, replace
from typing import Dict, Optional, Tuple

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


def shift_position(position, delta):
    return (
        float(position[0]) + float(delta[0]),
        float(position[1]) + float(delta[1]),
        float(position[2]) + float(delta[2]),
    )


def object_position(obj):
    return (float(obj.x), float(obj.y), float(obj.z))


class ChairRegistry:
    def __init__(self, max_match_distance):
        self.max_match_distance_sq = float(max_match_distance) ** 2
        self.next_chair_index = 0
        self.chairs: Dict[str, ObjectState] = {}

    def update(self, observations, selection, stamp):
        pairs = self._match_pairs(observations)
        assigned_indices = set()
        active_ids = {chair_id for chair_id, _ in pairs}
        anchor_delta = self._anchor_delta(pairs, observations)

        for chair_id, index in pairs:
            assigned_indices.add(index)
            self._update_existing(chair_id, observations[index], selection, stamp, anchor_delta)

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
                x=float(current.x) + float(anchor_delta[0]),
                y=float(current.y) + float(anchor_delta[1]),
                z=float(current.z) + float(anchor_delta[2]),
                stamp=stamp,
            )

        all_objects = sorted(self.chairs.values(), key=lambda item: item.object_id)
        return all_objects, dict(self.chairs)

    def _anchor_delta(self, pairs, observations):
        deltas = []
        for chair_id, index in pairs:
            observation = observations[index]
            if int(observation["state"]) != Detection3D.STATE_VISIBLE:
                continue
            current = self.chairs[chair_id]
            deltas.append(
                (
                    float(observation["x"]) - float(current.x),
                    float(observation["y"]) - float(current.y),
                    float(observation["z"]) - float(current.z),
                )
            )
        if not deltas:
            return (0.0, 0.0, 0.0)
        count = float(len(deltas))
        return (
            sum(item[0] for item in deltas) / count,
            sum(item[1] for item in deltas) / count,
            sum(item[2] for item in deltas) / count,
        )

    def _match_pairs(self, observations):
        candidates = []
        for chair_id, current in self.chairs.items():
            for index, observation in enumerate(observations):
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

    def _update_existing(self, chair_id, observation, selection, stamp, anchor_delta):
        current = self.chairs[chair_id]
        if int(observation["state"]) == Detection3D.STATE_VISIBLE:
            updated = self._chair_object(chair_id, observation, selection, stamp)
        else:
            x, y, z = shift_position(object_position(current), anchor_delta)
            updated = self._chair_object(
                chair_id,
                observation,
                selection,
                stamp,
                position=(x, y, z),
                frame_id=current.frame_id,
            )
        self.chairs[chair_id] = updated
        return updated

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
