#!/usr/bin/env python3
"""Shared helpers for Colt bridle scripts."""

import json
import math
from pathlib import Path

import cv2
import numpy as np
from colt_msgs.msg import Detection3D
from geometry_msgs.msg import Point
from sensor_msgs.msg import Image, JointState


def load_yaml(path, default=None):
    if default is None:
        default = {}
    path = Path(path)
    if not path.exists():
        return default
    import yaml

    with path.open("r", encoding="utf-8") as stream:
        return yaml.safe_load(stream) or {}


def load_json(path, default=None):
    if default is None:
        default = {}
    path = Path(path)
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def clamp(value, low, high):
    return max(low, min(high, value))


def time_to_float(stamp):
    return float(stamp.secs) + float(stamp.nsecs) * 1e-9


def header_to_dict(header):
    return {
        "seq": int(header.seq),
        "stamp": time_to_float(header.stamp),
        "frame_id": header.frame_id,
    }


def vector3_to_dict(value):
    return {"x": float(value.x), "y": float(value.y), "z": float(value.z)}


def quaternion_to_dict(value):
    return {
        "x": float(value.x),
        "y": float(value.y),
        "z": float(value.z),
        "w": float(value.w),
    }


def transform_to_dict(transform):
    return {
        "header": header_to_dict(transform.header),
        "child_frame_id": transform.child_frame_id,
        "translation": vector3_to_dict(transform.transform.translation),
        "rotation": quaternion_to_dict(transform.transform.rotation),
    }


def joint_state_to_dict(msg):
    if msg is None:
        return None
    return {
        "header": header_to_dict(msg.header),
        "name": list(msg.name),
        "position": [float(v) for v in msg.position],
        "velocity": [float(v) for v in msg.velocity],
        "effort": [float(v) for v in msg.effort],
    }


def camera_info_to_dict(msg):
    return {
        "header": header_to_dict(msg.header),
        "height": int(msg.height),
        "width": int(msg.width),
        "distortion_model": msg.distortion_model,
        "D": [float(v) for v in msg.D],
        "K": [float(v) for v in msg.K],
        "R": [float(v) for v in msg.R],
        "P": [float(v) for v in msg.P],
        "binning_x": int(msg.binning_x),
        "binning_y": int(msg.binning_y),
        "roi": {
            "x_offset": int(msg.roi.x_offset),
            "y_offset": int(msg.roi.y_offset),
            "height": int(msg.roi.height),
            "width": int(msg.roi.width),
            "do_rectify": bool(msg.roi.do_rectify),
        },
    }


def pointcloud_to_npz(path, msg):
    fields = msg.fields
    np.savez_compressed(
        path,
        data=np.frombuffer(msg.data, dtype=np.uint8),
        header=json.dumps(header_to_dict(msg.header), ensure_ascii=True),
        height=np.array(msg.height, dtype=np.uint32),
        width=np.array(msg.width, dtype=np.uint32),
        is_bigendian=np.array(msg.is_bigendian, dtype=np.bool_),
        point_step=np.array(msg.point_step, dtype=np.uint32),
        row_step=np.array(msg.row_step, dtype=np.uint32),
        is_dense=np.array(msg.is_dense, dtype=np.bool_),
        field_names=np.array([field.name for field in fields]),
        field_offsets=np.array([field.offset for field in fields], dtype=np.uint32),
        field_datatypes=np.array([field.datatype for field in fields], dtype=np.uint8),
        field_counts=np.array([field.count for field in fields], dtype=np.uint32),
    )


def image_to_bgr8(msg):
    if msg.encoding == "bgr8":
        array = np.frombuffer(msg.data, dtype=np.uint8).reshape(msg.height, msg.step)
        return np.ascontiguousarray(array[:, : msg.width * 3].reshape(msg.height, msg.width, 3))
    if msg.encoding == "rgb8":
        array = np.frombuffer(msg.data, dtype=np.uint8).reshape(msg.height, msg.step)
        rgb = array[:, : msg.width * 3].reshape(msg.height, msg.width, 3)
        return cv2.cvtColor(np.ascontiguousarray(rgb), cv2.COLOR_RGB2BGR)
    raise ValueError(f"unsupported color image encoding: {msg.encoding}")


def image_to_depth(msg):
    if msg.encoding in ("16UC1", "mono16"):
        dtype = np.uint16
    elif msg.encoding == "32FC1":
        dtype = np.float32
    else:
        raise ValueError(f"unsupported depth image encoding: {msg.encoding}")
    item_size = np.dtype(dtype).itemsize
    array = np.frombuffer(msg.data, dtype=dtype).reshape(msg.height, msg.step // item_size)
    return np.ascontiguousarray(array[:, : msg.width])


def bgr8_to_image(image, header):
    msg = Image()
    msg.header = header
    msg.height = int(image.shape[0])
    msg.width = int(image.shape[1])
    msg.encoding = "bgr8"
    msg.is_bigendian = False
    msg.step = int(image.shape[1] * 3)
    msg.data = image.astype(np.uint8).tobytes()
    return msg


def rotate_vector(vector, quat):
    q = np.array([quat.x, quat.y, quat.z], dtype=np.float64)
    v = np.array(vector, dtype=np.float64)
    return v + 2.0 * np.cross(q, np.cross(q, v) + float(quat.w) * v)


def project_pixel(x, y, z, camera_info):
    fx = float(camera_info.K[0])
    fy = float(camera_info.K[4])
    cx = float(camera_info.K[2])
    cy = float(camera_info.K[5])
    if z <= 0.0 or fx == 0.0 or fy == 0.0:
        return Point(x=0.0, y=0.0, z=0.0)
    return Point(x=(float(x) - cx) * z / fx, y=(float(y) - cy) * z / fy, z=z)


def expand_centered_box(shape, bbox, expand_ratio, min_width, min_height):
    height, width = shape
    x1, y1, x2, y2 = [float(value) for value in bbox]
    center_x = (x1 + x2) * 0.5
    center_y = (y1 + y2) * 0.5
    box_width = max((x2 - x1) * (1.0 + expand_ratio), float(min_width))
    box_height = max((y2 - y1) * (1.0 + expand_ratio), float(min_height))
    out_x1 = int(math.floor(clamp(center_x - box_width * 0.5, 0, width - 1)))
    out_y1 = int(math.floor(clamp(center_y - box_height * 0.5, 0, height - 1)))
    out_x2 = int(math.ceil(clamp(center_x + box_width * 0.5, out_x1 + 1, width)))
    out_y2 = int(math.ceil(clamp(center_y + box_height * 0.5, out_y1 + 1, height)))
    return (out_x1, out_y1, out_x2, out_y2)


def detection_by_id(detections, object_id, object_type="chair"):
    for item in detections:
        if item.id == object_id and item.object_type == object_type:
            return item
    return None


def joint_state_command(names, positions, velocity, stamp):
    command = JointState()
    command.header.stamp = stamp
    command.name = list(names)
    command.position = [float(value) for value in positions]
    command.velocity = [float(velocity) for _ in positions]
    return command
