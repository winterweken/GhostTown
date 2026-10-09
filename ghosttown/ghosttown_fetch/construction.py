"""Building permits as status points (design/development-applications.md §4.3).

A live permit (Inspection or Permit Issued, issued within LIVE_YEARS) is a
building under construction; a completed one (Closed on or after 1 January
of the massing year, issued at most BUILT_ISSUED_YEARS before it closed)
is a recent building. Houses are left out (counted for a note). A permit
has no geometry: it is placed at the City address point its GEO_ID names,
else at the one with the same street number and street name; one placed by
neither is outside the circle, or, when its street runs through the circle
at its number, unplaced (counted for a note).

Ported from BHPlus bh_context/construction.py (60d801e).
"""
import re

from .sources import ckan
from .sources.toronto_permits import FLOOR_FIELDS, LIVE_STATUSES

LIVE_YEARS = 6                    # older "Inspection" permits are mostly finished buildings never closed
BUILT_ISSUED_YEARS = 10           # a closure this long after issue is the City tidying its records
HOUSE_STRUCTURES = ("SFD", "2 Unit", "3+ Unit")
_LEADING_NUMBER = re.compile(r"^\s*0*(\d+)")
_NOT_IN_A_NAME = re.compile(r"['.]")


def _text(value):
    return value.strip() if isinstance(value, str) else ""


def years_before(iso, n):
    """The 'YYYY-MM-DD' `n` years before `iso` (29 February becomes the 28th)."""
    year, month, day = (int(p) for p in iso.split("-"))
    if month == 2 and day == 29:
        day = 28
    return "{0:04d}-{1:02d}-{2:02d}".format(year - n, month, day)


def is_house(row):
    """Whether a permit is for a house: "New Houses", or a house structure."""
    return _text(row.get("PERMIT_TYPE")) == "New Houses" or _text(row.get("STRUCTURE_TYPE")).startswith(
        HOUSE_STRUCTURES)


def fold(rows):
    """One row per PERMIT_NUM: its "00" row when there is one, else its lowest revision; in first-seen order."""
    best, order = {}, []
    for row in rows:
        number = _text(row.get("PERMIT_NUM"))
        if not number:
            continue
        if number not in best:
            order.append(number)
            best[number] = row
        elif _text(row.get("REVISION_NUM")) < _text(best[number].get("REVISION_NUM")):
            best[number] = row
    return [best[n] for n in order]


def live(rows, today):
    """The folded permits in a live status issued on or after LIVE_YEARS before `today`."""
    since = years_before(today, LIVE_YEARS)
    return [r for r in fold(rows) if _text(r.get("STATUS")) in LIVE_STATUSES
            and (ckan.day(r.get("ISSUED_DATE")) or "") >= since]


def completed(rows, year):
    """The folded Closed permits completed on or after 1 January `year`, issued at most BUILT_ISSUED_YEARS
    before they completed."""
    since = "{0}-01-01".format(year)
    out = []
    for r in fold(rows):
        done, issued = ckan.day(r.get("COMPLETED_DATE")), ckan.day(r.get("ISSUED_DATE"))
        if _text(r.get("STATUS")) == "Closed" and done and issued and done >= since \
                and issued >= years_before(done, BUILT_ISSUED_YEARS):
            out.append(r)
    return out


def floor_area(row):
    """The permit's floor area in m², its uses added up; a value that is not a number counts 0."""
    total = 0.0
    for field in FLOOR_FIELDS:
        value = row.get(field)
        if isinstance(value, str):
            try:
                value = float(value)
            except ValueError:
                continue
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value == value and value > 0:
            total += float(value)
    return total


def _number(value):
    m = _LEADING_NUMBER.match(value if isinstance(value, str) else str(value) if isinstance(value, int) else "")
    return m.group(1) if m else ""


def _street(name):
    return " ".join(_NOT_IN_A_NAME.sub("", _text(name)).upper().split())


def _id(value):
    if isinstance(value, bool):
        return ""
    if isinstance(value, (int, float)) and value == value:
        return str(int(value))
    text = _text(value)
    return text if text.isdigit() else ""


class Addresses:
    """The City address points around the site, found by id or by street number and name."""

    def __init__(self, features):
        self.by_id, self.by_street, self.numbers = {}, {}, {}
        for g, p in sorted(features, key=lambda gp: _id(gp[1].get("ADDRESS_POINT_ID")).zfill(12)):
            if g.geom_type != "Point":
                continue
            pid, number, street = _id(p.get("ADDRESS_POINT_ID")), _number(p.get("LO_NUM")), _street(
                p.get("LINEAR_NAME"))
            if pid:
                self.by_id.setdefault(pid, g)
            if number and street:
                self.by_street.setdefault((number, street), []).append(
                    (g, _text(p.get("LINEAR_NAME_TYPE")).upper(), _text(p.get("LINEAR_NAME_DIR")).upper()))
                self.numbers.setdefault(street, []).append((int(number), _text(p.get("LINEAR_NAME_DIR")).upper()))

    def locate(self, row):
        """The address point of a permit, or None."""
        g = self.by_id.get(_id(row.get("GEO_ID")))
        if g is not None:
            return g
        kind, direction = _text(row.get("STREET_TYPE")).upper(), _text(row.get("STREET_DIRECTION")).upper()
        for g, its_kind, its_direction in self.by_street.get((_number(row.get("STREET_NUM")),
                                                              _street(row.get("STREET_NAME"))), []):
            if (not kind or not its_kind or kind == its_kind) and (
                    not direction or not its_direction or direction == its_direction):
                return g
        return None

    def nearby(self, row):
        """Whether a permit's street runs through here at its number (between the lowest and highest
        address numbers this street has here, in its direction when both say one), so not finding it means
        its address is missing."""
        direction, number = _text(row.get("STREET_DIRECTION")).upper(), _number(row.get("STREET_NUM"))
        numbers = [n for n, its in self.numbers.get(_street(row.get("STREET_NAME")), [])
                   if not direction or not its or direction == its]
        return bool(numbers and number) and min(numbers) <= int(number) <= max(numbers)


def _address(row):
    return " ".join(t for t in (_text(row.get(k)) for k in ("STREET_NUM", "STREET_NAME", "STREET_TYPE",
                                                             "STREET_DIRECTION")) if t)


def points(rows, group, addresses, keep):
    """([(point, status point)], houses, unplaced) of permits (already cut
    by live() or completed()) in `group` ("construction" or "built"):
    each kept one placed, houses counted rather than kept, and those whose
    street runs through here but whose address is not found counted."""
    out, houses, unplaced = [], 0, 0
    for row in rows:
        g = addresses.locate(row)
        if g is None:
            unplaced += int(not is_house(row) and addresses.nearby(row))
            continue
        if not keep(g):
            continue
        if is_house(row):
            houses += 1
            continue
        date = ckan.day(row.get("COMPLETED_DATE" if group == "built" else "ISSUED_DATE")) or ""
        out.append((g, {"number": _text(row.get("PERMIT_NUM")), "source": "permit", "group": group,
                        "type": _text(row.get("STRUCTURE_TYPE")), "status": _text(row.get("STATUS")), "date": date,
                        "description": _text(row.get("DESCRIPTION")), "address": _address(row),
                        "floor_area_m2": round(floor_area(row), 1), "folderrsn": "", "unknown": None, "url": ""}))
    return out, houses, unplaced
