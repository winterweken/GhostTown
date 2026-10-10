"""The City of Toronto's old survey grid (NAD27, MTM zone 10) to lon/lat. The City's development applications
table gives its points only as X/Y on that grid. A quadratic in X and Y, fitted for BHPlus on all 15,683 points of
the City's applications map layer (which carries each point's NAD27 X/Y beside its longitude and latitude), is
within 1.01 m anywhere in the City, median 0.17 m; a plain affine is 40 m out at the edges. Good inside Toronto
only. Ported from BHPlus bh_context/mtm.py (60d801e). Standard library only."""
X0, Y0 = 315000.0, 4840000.0       # the fit's origin; its terms are in kilometres from it
LON = (-79.37325191775103, 0.0124071203594951, 1.8840177570581942e-05, -4.1180539278887763e-10,
       1.8640172725799175e-06, -6.313294613144159e-09)
LAT = (43.7018799591393, -1.3668036939638655e-05, 0.009001308169981952, -6.710819506449647e-07,
       -7.401185141775182e-09, 5.20160818360635e-09)


def to_lonlat(x, y):
    """(lon, lat) of NAD27 MTM zone 10 (x, y) in metres."""
    u, v = (x - X0) / 1000.0, (y - Y0) / 1000.0
    terms = (1.0, u, v, u * u, u * v, v * v)
    return sum(c * t for c, t in zip(LON, terms)), sum(c * t for c, t in zip(LAT, terms))
