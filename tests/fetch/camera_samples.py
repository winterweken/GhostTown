import math

import numpy as np


def look_at(heading_deg, pitch_deg=0.0):
    """World-to-camera rotation for a camera looking along a compass heading (0 = north, clockwise) and
    tilted up by pitch: rows are the camera's right, down and forward axes."""
    h, p = math.radians(heading_deg), math.radians(pitch_deg)
    forward = np.array([math.sin(h) * math.cos(p), math.cos(h) * math.cos(p), math.sin(p)])
    right = np.array([math.cos(h), -math.sin(h), 0.0])
    down = np.cross(forward, right)
    return np.array([right, down, forward])


def rotation_vector(R):
    """Axis-angle vector of a rotation matrix. Not for half turns, which the tests never use."""
    angle = math.acos(max(-1.0, min(1.0, (np.trace(R) - 1) / 2)))
    if angle < 1e-9:
        return [0.0, 0.0, 0.0]
    axis = np.array([R[2, 1] - R[1, 2], R[0, 2] - R[2, 0], R[1, 0] - R[0, 1]]) / (2 * math.sin(angle))
    return (axis * angle).tolist()


def camera(position, heading_deg=0.0, pitch_deg=0.0, *, kind="perspective", focal=0.6, k1=0.0, k2=0.0,
           width=2048, height=1536, year=2024, image_id="c1"):
    from ghosttown_fetch.camera import Camera

    return Camera(image_id, kind, position, look_at(heading_deg, pitch_deg), focal=focal, k1=k1, k2=k2,
                  width=width, height=height, year=year)
