"""The City's building permits for new buildings (CKAN): the live ones (Inspection, Permit Issued) newest issued
first, and the completed ones (Closed) newest completed first, each read back only to a cutoff day, with the row id
breaking ties so the pages neither skip nor repeat a row. An empty list is refused (the City always has some).
Ported from BHPlus bh_context/sources/permits.py."""
from . import ckan

LIVE = "6d0229af-bc54-46de-9c2b-26759b01dd05"          # building-permits-active-permits
DONE = "a96c0ba4-3026-402b-b09d-5b1268b8f810"          # building-permits-cleared-permits, since 2017
WHAT = "building permits"
LIVE_STATUSES = ("Inspection", "Permit Issued")
FLOOR_FIELDS = ("ASSEMBLY", "INSTITUTIONAL", "RESIDENTIAL", "BUSINESS_AND_PERSONAL_SERVICES", "MERCANTILE",
                "INDUSTRIAL")                               # floor area by use, m²
FIELDS = ("PERMIT_NUM", "REVISION_NUM", "PERMIT_TYPE", "STRUCTURE_TYPE", "STATUS", "GEO_ID", "STREET_NUM",
          "STREET_NAME", "STREET_TYPE", "STREET_DIRECTION", "ISSUED_DATE", "COMPLETED_DATE",
          "DESCRIPTION") + FLOOR_FIELDS


def _before(value, since):
    d = ckan.day(value)
    return d is not None and d < since


def _get(net, resource, filters, field, since, today):
    return ckan.none_is_wrong(ckan.read(net, resource, WHAT, today, filters=filters, fields=FIELDS,
                                        sort=field + " desc, _id", stop=lambda row: _before(row.get(field), since)),
                              WHAT)


def get_live(net, since, today):
    """Live new-building permits issued on or after `since` ('YYYY-MM-DD'), newest first, with any whose issued
    date is missing."""
    return _get(net, LIVE, {"WORK": "New Building", "STATUS": list(LIVE_STATUSES)}, "ISSUED_DATE", since, today)


def get_completed(net, since, today):
    """New-building permits closed on or after `since`, newest first."""
    return _get(net, DONE, {"WORK": "New Building", "STATUS": "Closed"}, "COMPLETED_DATE", since, today)
