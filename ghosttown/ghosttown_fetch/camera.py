"""Mapillary cameras in the site's local frame (x east, y north, z up): where they stand, where they look,
and where a point lands in the picture. Picture positions are fractions of width and height from the
top-left corner, the same for the original and the thumbnail."""
import math
import time

import numpy as np

MOUNT_M = 2.0     # camera height above the ground; Mapillary's altitudes are unreliable
THUMB_PX = 2048   # long side of the thumbnails Street Look downloads
MAX_R2 = 1.2      # perspective points further out than this sit in the lens's untrustworthy corners
KINDS = ("perspective", "fisheye", "spherical")


def rotvec_to_matrix(r):
    """Rotation matrix of an axis-angle vector (Rodrigues' formula)."""
    r = np.asarray(r, dtype=float)
    theta = float(np.linalg.norm(r))
    if theta < 1e-12:
        return np.eye(3)
    k = r / theta
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + math.sin(theta) * K + (1 - math.cos(theta)) * K @ K


class Camera:
    """R turns world offsets into camera axes: x right, y down, z forward (OpenSfM's convention, which
    Mapillary's computed_rotation uses)."""

    def __init__(self, image_id, kind, position, R, *, focal=0.0, k1=0.0, k2=0.0, width, height, year,
                 sequence=""):
        self.id = str(image_id)
        self.kind = kind
        self.position = np.asarray(position, dtype=float)
        self.R = np.asarray(R, dtype=float)
        self.focal, self.k1, self.k2 = float(focal), float(k1), float(k2)
        self.width, self.height = int(width), int(height)
        self.year = int(year)
        self.sequence = sequence

    @classmethod
    def from_mapillary(cls, image, frame, terrain):
        """A Camera from one of Mapillary's image records, or None when it lacks what Street Look needs."""
        try:
            lon, lat = (float(c) for c in image["computed_geometry"]["coordinates"][:2])
            rotation = [float(c) for c in image["computed_rotation"]]
            kind = image["camera_type"]
            width, height = int(image["width"]), int(image["height"])
            year = time.gmtime(image["captured_at"] / 1000).tm_year
            params = [float(p) for p in (image.get("camera_parameters") or [])]
        except (KeyError, TypeError, ValueError, IndexError, OverflowError):
            return None
        if kind not in KINDS or width <= 0 or height <= 0 or len(rotation) != 3:
            return None
        if kind != "spherical" and not (params and params[0] > 0):
            return None
        x, y = frame.to_local(lon, lat)
        z = float(terrain.z(np.array([x]), np.array([y]))[0]) + MOUNT_M
        return cls(image["id"], kind, (x, y, z), rotvec_to_matrix(rotation),
                   focal=params[0] if params else 0.0, k1=params[1] if len(params) > 1 else 0.0,
                   k2=params[2] if len(params) > 2 else 0.0, width=width, height=height, year=year,
                   sequence=image.get("sequence") or "")

    @property
    def forward(self):
        return self.R[2]

    def pitch_deg(self):
        return math.degrees(math.asin(max(-1.0, min(1.0, float(self.forward[2])))))

    def project(self, points):
        """(u, v, ok) for (n, 3) points: picture fractions, and whether the point is in front of the camera
        in a trustworthy part of the lens. u and v can fall outside 0..1."""
        X = (np.asarray(points, dtype=float).reshape(-1, 3) - self.position) @ self.R.T
        if self.kind == "spherical":
            lon = np.arctan2(X[:, 0], X[:, 2])
            lat = np.arctan2(-X[:, 1], np.hypot(X[:, 0], X[:, 2]))
            u = lon / (2 * np.pi) + 0.5
            v = 0.5 - lat * self.width / (2 * np.pi * self.height)
            return u, v, np.ones(len(X), dtype=bool)
        z = X[:, 2]
        ok = z > 0.5
        zz = np.where(ok, z, 1.0)
        xn, yn = X[:, 0] / zz, X[:, 1] / zz
        if self.kind == "fisheye":
            r = np.hypot(xn, yn)
            th = np.arctan(r)
            s = np.where(r > 1e-9, th * (1 + self.k1 * th ** 2 + self.k2 * th ** 4) / np.maximum(r, 1e-9), 1.0)
        else:
            r2 = xn ** 2 + yn ** 2
            ok &= r2 < MAX_R2
            s = 1 + self.k1 * r2 + self.k2 * r2 ** 2
        side = max(self.width, self.height)
        u = self.focal * s * xn * side / self.width + 0.5
        v = self.focal * s * yn * side / self.height + 0.5
        return u, v, ok

    def pixels_per_metre(self, points, cos_incidence):
        """Thumbnail pixels per metre of wall at each point, shrunk by how obliquely the wall is seen."""
        dist = np.linalg.norm(np.asarray(points, dtype=float).reshape(-1, 3) - self.position, axis=1)
        if self.kind == "spherical":
            f_px = THUMB_PX * self.width / max(self.width, self.height) / (2 * np.pi)
        else:
            f_px = self.focal * THUMB_PX
        return f_px / np.maximum(dist, 1e-6) * np.asarray(cos_incidence, dtype=float)

    def rays(self, grid_w):
        """(directions, rows): unit world directions through the centres of a grid_w-wide pixel grid, row
        by row from the top-left."""
        rows = max(1, round(grid_w * self.height / self.width))
        U, V = np.meshgrid((np.arange(grid_w) + 0.5) / grid_w, (np.arange(rows) + 0.5) / rows)
        if self.kind == "spherical":
            lon = (U - 0.5) * 2 * np.pi
            lat = (0.5 - V) * 2 * np.pi * self.height / self.width
            X = np.stack([np.sin(lon) * np.cos(lat), -np.sin(lat), np.cos(lon) * np.cos(lat)], -1)
        else:
            side = max(self.width, self.height)
            xd = (U - 0.5) * self.width / (self.focal * side)
            yd = (V - 0.5) * self.height / (self.focal * side)
            if self.kind == "fisheye":
                rd = np.hypot(xd, yd)
                th = np.minimum(rd, 1.5)
                for _ in range(30):   # solve th * (1 + k1 th^2 + k2 th^4) = rd
                    f = th * (1 + self.k1 * th ** 2 + self.k2 * th ** 4) - rd
                    df = 1 + 3 * self.k1 * th ** 2 + 5 * self.k2 * th ** 4
                    th = th - f / np.where(np.abs(df) > 1e-9, df, 1e-9)
                scale = np.where(rd > 1e-9, np.tan(np.clip(th, 0.0, 1.5)) / np.maximum(rd, 1e-9), 1.0)
                xn, yn = xd * scale, yd * scale
            else:
                xn, yn = xd.copy(), yd.copy()
                for _ in range(20):   # undo the radial distortion
                    r2 = xn ** 2 + yn ** 2
                    s = 1 + self.k1 * r2 + self.k2 * r2 ** 2
                    xn, yn = xd / s, yd / s
            X = np.stack([xn, yn, np.ones_like(xn)], -1)
        D = X.reshape(-1, 3) @ self.R
        return D / np.linalg.norm(D, axis=1, keepdims=True), rows
