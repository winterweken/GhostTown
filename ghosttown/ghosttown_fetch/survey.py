"""Survey grid coordinates of the site origin, for Revit's survey point. Standard library only.

The model stays at a local origin; this only says where that origin is on a survey grid. Toronto
uses the City's grid, NAD83(CSRS) / MTM zone 10 (EPSG:2952); everywhere else gets the site's UTM
zone on WGS 84. Latitude and longitude are used as given: NAD83(CSRS) and WGS 84 differ by 1-2 m in
Canada today, so this lines up context, not a legal survey.

Transverse Mercator by Krüger's series to sixth order in n (Karney 2011), which agrees with PROJ to
well under a millimetre across a zone.
"""
import math
from collections import namedtuple

GRS80 = (6378137.0, 1 / 298.257222101)
WGS84 = (6378137.0, 1 / 298.257223563)

Grid = namedtuple("Grid", "epsg name lon0 k0 false_easting false_northing ellipsoid")

MTM10 = Grid(2952, "NAD83(CSRS) / MTM zone 10", -79.5, 0.9999, 304800.0, 0.0, GRS80)


def utm(lat, lon):
    """The UTM zone for a point, with the Norway and Svalbard exceptions."""
    zone = min(int((lon + 180.0) // 6.0) + 1, 60)
    if 56.0 <= lat < 64.0 and 3.0 <= lon < 12.0:
        zone = 32
    elif lat >= 72.0 and 0.0 <= lon < 42.0:
        zone = 31 if lon < 9.0 else 33 if lon < 21.0 else 35 if lon < 33.0 else 37
    north = lat >= 0.0
    return Grid((32600 if north else 32700) + zone, f"WGS 84 / UTM zone {zone}{'N' if north else 'S'}",
                zone * 6.0 - 183.0, 0.9996, 500000.0, 0.0 if north else 10000000.0, WGS84)


def grid_for(region, lat, lon):
    return MTM10 if region == "toronto" else utm(lat, lon)


def _alphas(n):
    return (
        n / 2 - 2 * n**2 / 3 + 5 * n**3 / 16 + 41 * n**4 / 180 - 127 * n**5 / 288 + 7891 * n**6 / 37800,
        13 * n**2 / 48 - 3 * n**3 / 5 + 557 * n**4 / 1440 + 281 * n**5 / 630 - 1983433 * n**6 / 1935360,
        61 * n**3 / 240 - 103 * n**4 / 140 + 15061 * n**5 / 26880 + 167603 * n**6 / 181440,
        49561 * n**4 / 161280 - 179 * n**5 / 168 + 6601661 * n**6 / 7257600,
        34729 * n**5 / 80640 - 3418889 * n**6 / 1995840,
        212378941 * n**6 / 319334400,
    )


def project(grid, lat, lon):
    """(easting m, northing m, grid angle in degrees: + means grid north lies east of true north)."""
    a, f = grid.ellipsoid
    n = f / (2 - f)
    big_a = a / (1 + n) * (1 + n**2 / 4 + n**4 / 64 + n**6 / 256)
    e = 2 * math.sqrt(n) / (1 + n)
    phi, lam = math.radians(lat), math.radians(lon - grid.lon0)
    t = math.sinh(math.atanh(math.sin(phi)) - e * math.atanh(e * math.sin(phi)))
    xi1, eta1 = math.atan2(t, math.cos(lam)), math.atanh(math.sin(lam) / math.sqrt(1 + t * t))
    xi, eta, p, q = xi1, eta1, 1.0, 0.0
    for j, alpha in enumerate(_alphas(n), start=1):
        s, c = math.sin(2 * j * xi1), math.cos(2 * j * xi1)
        sh, ch = math.sinh(2 * j * eta1), math.cosh(2 * j * eta1)
        xi += alpha * s * ch
        eta += alpha * c * sh
        p += 2 * j * alpha * c * ch
        q += 2 * j * alpha * s * sh
    gamma = math.atan(t / math.sqrt(1 + t * t) * math.tan(lam)) + math.atan2(q, p)
    return (grid.false_easting + grid.k0 * big_a * eta,
            grid.false_northing + grid.k0 * big_a * xi,
            math.degrees(gamma))


def survey_point(region, lat, lon, elevation_m):
    """What context.json records under "survey"; elevation_m is None when the ground level is unknown."""
    grid = grid_for(region, lat, lon)
    easting, northing, angle = project(grid, lat, lon)
    return {"epsg": f"EPSG:{grid.epsg}", "name": grid.name, "easting_m": round(easting, 3),
            "northing_m": round(northing, 3),
            "elevation_m": None if elevation_m is None else round(float(elevation_m), 3),
            "grid_angle_deg": round(angle, 6)}
