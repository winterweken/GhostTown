"""Answers shaped like the City of Toronto's CKAN datastore_search, served from rows held in memory."""
import json
import urllib.parse

from ghosttown_fetch import mtm27


def query(url):
    return {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlsplit(url).query).items()}


def answer(tables):
    """A FakeNet answer for datastore_search over `tables` ({resource id: rows, in the order the City sorts them}):
    rows matched by `filters` (a list means any of its values), cut to `fields`, paged by offset and limit."""
    def serve(url, data):
        q = query(url)
        rows = tables[q["resource_id"]]
        for key, want in json.loads(q.get("filters", "{}")).items():
            allowed = want if isinstance(want, list) else [want]
            rows = [r for r in rows if r.get(key) in allowed]
        if q.get("fields"):
            rows = [{k: r.get(k) for k in q["fields"].split(",")} for r in rows]
        start, limit = int(q["offset"]), int(q["limit"])
        return json.dumps({"success": True, "result": {"records": rows[start:start + limit],
                                                       "total": len(rows)}}).encode("utf-8")
    return serve


def mtm27_xy(lon, lat):
    """The NAD27 MTM zone 10 X/Y that mtm27.to_lonlat takes to (lon, lat), found by Newton's method."""
    x, y = 314092.389, 4833631.921
    for _ in range(8):
        lo, la = mtm27.to_lonlat(x, y)
        ax, ay = mtm27.to_lonlat(x + 1.0, y)
        bx, by = mtm27.to_lonlat(x, y + 1.0)
        a, b, c, d = ax - lo, bx - lo, ay - la, by - la      # d(lon, lat) / d(x, y), per metre
        det = a * d - b * c
        ex, ey = lon - lo, lat - la
        x += (ex * d - ey * b) / det
        y += (ey * a - ex * c) / det
    return x, y
