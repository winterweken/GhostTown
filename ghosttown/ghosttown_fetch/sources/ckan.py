"""The City of Toronto's Open Data tables (CKAN datastore_search), read page by page in a given order until a row
says stop. Every page must be a list of flat records (text, numbers, true/false or nothing) before any of it is
used or cached; a page that comes back empty before the table's total, or a total that changes between pages (the
City reloading the table), is refused rather than taken as the whole table; and a table that runs past MAX_ROWS is
refused rather than read on forever. Pages are kept for the day they were read: the cache key carries the day, so
the pages of one read never mix two days of the City's table. Ported from BHPlus bh_context/sources/ckan.py."""
import json
import math
import re
import urllib.parse

from ..net import SourceError

SEARCH = "https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/datastore_search"
SOURCE = "toronto"
PAGE_SIZE = 10000
MAX_ROWS = 50000
MAX_AGE_DAYS = 1          # the City refreshes these tables daily
_DAY = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:$|T)")


def search_url(resource, offset=0, filters=None, fields=None, sort=None, limit=None):
    """The datastore_search URL for one page of `resource`."""
    params = [("resource_id", resource), ("limit", PAGE_SIZE if limit is None else limit), ("offset", offset)]
    if filters:
        params.append(("filters", json.dumps(filters, sort_keys=True)))
    if fields:
        params.append(("fields", ",".join(fields)))
    if sort:
        params.append(("sort", sort))
    return SEARCH + "?" + urllib.parse.urlencode(params)


def _value_ok(v):
    return v is None or isinstance(v, (str, bool, int)) or (isinstance(v, float) and math.isfinite(v))


def rows_ok(rows):
    """Whether `rows` is a list of flat records whose keys are text."""
    return isinstance(rows, list) and all(
        isinstance(r, dict) and all(isinstance(k, str) and _value_ok(v) for k, v in r.items()) for r in rows)


def _page(body, what):
    """A page's `result` ({"records", "total"}), or a SourceError naming the table."""
    try:
        page = json.loads(body)
    except ValueError:
        page = None
    result = page.get("result") if isinstance(page, dict) else None
    total = result.get("total") if isinstance(result, dict) else None
    if not (isinstance(result, dict) and rows_ok(result.get("records")) and isinstance(total, int)
            and not isinstance(total, bool)):
        raise SourceError(f"The City's Open Data portal sent an answer for its {what} that couldn't be read; "
                          "try again later.")
    return result


def read(net, resource, what, today, *, filters=None, fields=None, sort=None, stop=None, max_rows=MAX_ROWS):
    """Every row of `resource` matching `filters`, in `sort` order, until `stop(row)` is true (that row and every
    one after it are left unread). `what` names the table in the errors ("building permits"); `today`
    ('YYYY-MM-DD') keys the cached pages."""
    rows, offset, total = [], 0, None

    def check(body):
        _page(body, what)

    while True:
        url = search_url(resource, offset, filters, fields, sort)
        result = _page(net.get(url, source=SOURCE, check=check, key=url + "\n" + today, max_age_days=MAX_AGE_DAYS),
                       what)
        records = result["records"]
        if total is not None and result["total"] != total:
            raise SourceError(f"The City's {what} changed while they were read; try again later.")
        total = result["total"]
        if not records and offset < total:
            raise SourceError(f"The City's Open Data portal sent fewer rows of its {what} than it said it has; "
                              "try again later.")
        for row in records:
            if stop is not None and stop(row):
                return rows
            if len(rows) >= max_rows:
                raise SourceError(f"The City's {what} have more than {max_rows:,} rows to read; try again later.")
            rows.append(row)
        offset += len(records)
        if not records or offset >= total:
            return rows


def none_is_wrong(rows, what):
    """`rows`, or a SourceError when a list that is never empty (the whole City's) came back empty."""
    if not rows:
        raise SourceError(f"The City's Open Data portal sent no rows for its {what}; try again later.")
    return rows


def day(value):
    """The 'YYYY-MM-DD' a CKAN date text starts with ('2026-03-09T00:00:00' too), else None."""
    m = _DAY.match(value) if isinstance(value, str) else None
    return m.group(1) if m else None
