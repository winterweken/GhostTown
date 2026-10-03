"""Local metric frame around a centre point: x east, y north, in metres.

A plain equirectangular frame scaled by the WGS84 radii of curvature at the
centre latitude. Within 1 km of the centre it agrees with geodesic distances to
a few millimetres, which is far below the accuracy of the source data.
"""
import math

import numpy as np

A = 6378137.0                # WGS84 semi-major axis, m
F = 1 / 298.257223563        # WGS84 flattening
E2 = F * (2 - F)             # first eccentricity squared


class Frame:
    def __init__(self, lat0, lon0):
        self.lat0 = float(lat0)
        self.lon0 = float(lon0)
        phi = math.radians(self.lat0)
        w = 1.0 - E2 * math.sin(phi) ** 2
        meridian = A * (1.0 - E2) / w ** 1.5    # radius of curvature north-south
        normal = A / math.sqrt(w)              # radius of curvature east-west
        self.ky = meridian * math.pi / 180.0   # metres per degree of latitude
        self.kx = normal * math.cos(phi) * math.pi / 180.0  # metres per degree of longitude

    def to_local(self, lon, lat):
        return (lon - self.lon0) * self.kx, (lat - self.lat0) * self.ky

    def to_lonlat(self, x, y):
        return self.lon0 + x / self.kx, self.lat0 + y / self.ky


def lonlat_to_merc(lon, lat):
    """Web Mercator (EPSG:3857) metres from lon/lat degrees; floats or numpy arrays."""
    lon = np.asarray(lon, dtype=float)
    lat = np.asarray(lat, dtype=float)
    return A * np.radians(lon), A * np.log(np.tan(np.pi / 4 + np.radians(lat) / 2))
