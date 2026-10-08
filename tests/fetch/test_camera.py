import math

import numpy as np
import pytest

from ghosttown_fetch.camera import Camera, rotvec_to_matrix
from ghosttown_fetch.frame import Frame
from ghosttown_fetch.terrain import FlatTerrain
from camera_samples import camera, look_at, rotation_vector


def test_rotation_vectors_round_trip():
    assert np.allclose(rotvec_to_matrix([0, 0, 0]), np.eye(3))
    for heading, pitch in ((0, 0), (30, 5), (-40, -8)):
        R = look_at(heading, pitch)
        assert np.allclose(rotvec_to_matrix(rotation_vector(R)), R, atol=1e-9)


def test_a_camera_facing_north_sees_north_ahead():
    cam = camera((0, 0, 2))
    assert np.allclose(cam.forward, [0, 1, 0]) and abs(cam.pitch_deg()) < 1e-9
    u, v, ok = cam.project(np.array([[0, 10, 2], [3, 10, 2], [0, 10, 5], [0, -10, 2]]))
    assert ok.tolist() == [True, True, True, False]
    assert abs(u[0] - 0.5) < 1e-9 and abs(v[0] - 0.5) < 1e-9
    assert u[1] > 0.5 and v[2] < 0.5


def test_pitch_is_measured_from_level():
    assert abs(camera((0, 0, 2), pitch_deg=10).pitch_deg() - 10) < 1e-9


@pytest.mark.parametrize("kind,k1,k2,height", [("perspective", -0.1, 0.02, 1200), ("fisheye", 0.05, -0.01, 1200),
                                               ("spherical", 0.0, 0.0, 800)])
def test_rays_land_back_on_their_pixels(kind, k1, k2, height):
    cam = camera((5, -3, 2), heading_deg=20, pitch_deg=4, kind=kind, k1=k1, k2=k2, width=1600, height=height)
    dirs, rows = cam.rays(40)
    u, v, ok = cam.project(cam.position + dirs * 25.0)
    gu, gv = np.meshgrid((np.arange(40) + 0.5) / 40, (np.arange(rows) + 0.5) / rows)
    assert ok.mean() > 0.9
    assert np.allclose(u[ok], gu.ravel()[ok], atol=1e-6) and np.allclose(v[ok], gv.ravel()[ok], atol=1e-6)


def test_pixels_per_metre_falls_with_distance_and_angle():
    cam = camera((0, 0, 2))
    ppm = cam.pixels_per_metre(np.array([[0, 100, 2], [0, 50, 2]]), np.array([1.0, 0.5]))
    assert np.allclose(ppm, [0.6 * 2048 / 100, 0.6 * 2048 / 50 * 0.5])
    pano = camera((0, 0, 2), kind="spherical", width=4000, height=2000)
    assert np.isclose(pano.pixels_per_metre(np.array([[0, 100, 2]]), np.array([1.0]))[0], 2048 / (2 * math.pi) / 100)


RECORD = {"id": 77, "captured_at": 1717200000000, "camera_type": "perspective",
          "computed_geometry": {"type": "Point", "coordinates": [-79.38, 43.65]},
          "computed_rotation": [1.2, 0.0, 0.0], "camera_parameters": [0.55, -0.1, 0.01],
          "width": 4000, "height": 3000, "sequence": "abc"}


def test_from_mapillary_places_the_camera_on_the_ground():
    cam = Camera.from_mapillary(RECORD, Frame(43.65, -79.38), FlatTerrain())
    assert cam.id == "77" and cam.kind == "perspective" and cam.year == 2024 and cam.sequence == "abc"
    assert np.allclose(cam.position, [0, 0, 2.0]) and (cam.focal, cam.k1, cam.k2) == (0.55, -0.1, 0.01)
    # Pin the rotation convention: R[2] is forward; computed_rotation [1.2, 0, 0] is x-axis rotation
    assert np.allclose(cam.forward, [0, math.sin(1.2), math.cos(1.2)], atol=1e-9)
    assert np.isclose(cam.pitch_deg(), math.degrees(math.asin(math.cos(1.2))), atol=1e-9)


@pytest.mark.parametrize("change", [{"camera_parameters": None}, {"camera_type": "panorama"},
                                    {"computed_rotation": None}, {"width": 0}, {"computed_geometry": None},
                                    {"computed_geometry": {"coordinates": ["x", 43.65]}}])
def test_from_mapillary_skips_records_it_cannot_use(change):
    record = dict(RECORD)
    record.update(change)
    assert Camera.from_mapillary(record, Frame(43.65, -79.38), FlatTerrain()) is None


class StubTerrain:
    """Terrain stub that always returns z=5.0."""
    def z(self, xs, ys):
        return np.full_like(xs, 5.0, dtype=float)


def test_from_mapillary_uses_terrain_for_z():
    """Terrain z value (5.0) + MOUNT_M (2.0) = position z (7.0)."""
    cam = Camera.from_mapillary(RECORD, Frame(43.65, -79.38), StubTerrain())
    assert np.isclose(cam.position[2], 7.0)


def test_from_mapillary_handles_spherical_camera():
    """Spherical cameras (no focal length requirement) are parsed correctly."""
    record = dict(RECORD)
    record.update({"camera_type": "spherical", "camera_parameters": None})
    cam = Camera.from_mapillary(record, Frame(43.65, -79.38), FlatTerrain())
    assert cam is not None and cam.kind == "spherical"


def test_from_mapillary_handles_fisheye_camera():
    """Fisheye cameras with distortion coefficients are parsed correctly."""
    record = dict(RECORD)
    record.update({"camera_type": "fisheye", "camera_parameters": [0.5, 0.1, -0.02]})
    cam = Camera.from_mapillary(record, Frame(43.65, -79.38), FlatTerrain())
    assert cam is not None and cam.kind == "fisheye" and cam.k1 == 0.1 and cam.k2 == -0.02


def test_perspective_point_with_large_r2_projects_with_ok_false():
    """Points with normalized r² > MAX_R2 (1.2) project with ok=False (outside trustworthy lens region)."""
    cam = camera((0, 0, 2), focal=0.6)   # looking north, so camera x is east and z is north
    _u, _v, ok = cam.project(np.array([[11, 10, 2]]))   # 10 m ahead, 11 m right: xn = 1.1, r² = 1.21
    assert not ok[0]
