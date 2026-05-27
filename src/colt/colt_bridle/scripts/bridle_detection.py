#!/usr/bin/env python3
"""Shared detection helpers for Colt bridle scripts."""

import numpy as np
import supervision as sv
from colt_msgs.msg import Detection3D

from bridle_common import expand_centered_box


CLASS_INDEX = {"chair": 0, "seat": 1, "item": 2}
OBJECT_TYPE_BY_CLASS = {
    "chair": "chair",
    "chair_seat": "seat",
    "aluminum_block": "item",
}


def roi_for_detection(image_shape, bbox, rule):
    return expand_centered_box(
        image_shape,
        bbox,
        float(rule.get("expand_ratio", 0.2)),
        float(rule.get("min_width_px", 96)),
        float(rule.get("min_height_px", 96)),
    )


def map_roi_detection(item, roi, image_shape):
    x1, y1, x2, y2 = roi
    full_mask = None
    if item["mask"] is not None:
        full_mask = np.zeros(image_shape, dtype=bool)
        full_mask[y1:y2, x1:x2] = item["mask"]
    return {
        "bbox": np.array(
            [item["bbox"][0] + x1, item["bbox"][1] + y1, item["bbox"][2] + x1, item["bbox"][3] + y1],
            dtype=np.float32,
        ),
        "confidence": item["confidence"],
        "class_name": item["class_name"],
        "mask": full_mask,
    }


def bbox_center(bbox):
    x1, y1, x2, y2 = bbox
    return int((x1 + x2) * 0.5), int((y1 + y2) * 0.5)


def center_window_region(shape, bbox, radius=3):
    height, width = shape[:2]
    center_x, center_y = bbox_center(bbox)
    region = np.zeros(shape, dtype=bool)
    region[
        max(0, center_y - radius) : min(height, center_y + radius + 1),
        max(0, center_x - radius) : min(width, center_x + radius + 1),
    ] = True
    return region


def object_type_for_class(class_name):
    return OBJECT_TYPE_BY_CLASS.get(class_name, class_name)


def state_for_detection(depth_valid, tf_ok, geometry_ok):
    return (
        Detection3D.STATE_VISIBLE
        if depth_valid and tf_ok and geometry_ok
        else Detection3D.STATE_VISIBLE_NO_DEPTH
    )


def supervision_payload(items):
    visible_items = [item for item in items if item.get("draw", False) and item.get("bbox") is not None]
    if not visible_items:
        return None, []
    xyxy = np.array([item["bbox"] for item in visible_items], dtype=np.float32)
    confidence = np.array([item["message"].confidence for item in visible_items], dtype=np.float32)
    class_id = np.array(
        [CLASS_INDEX.get(item["message"].object_type, 0) for item in visible_items], dtype=np.int32
    )
    labels = [
        f"{item['message'].id} {item['message'].object_type} {int(item['message'].state)}"
        for item in visible_items
    ]
    masks = [item["mask"].astype(bool) for item in visible_items if item["mask"] is not None]
    detections = sv.Detections(
        xyxy=xyxy,
        confidence=confidence,
        class_id=class_id,
        mask=np.stack(masks) if len(masks) == len(visible_items) and masks else None,
    )
    return detections, labels
