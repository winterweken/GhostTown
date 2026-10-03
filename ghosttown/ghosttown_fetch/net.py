"""HTTP for every source: identifying User-Agent, one retry for busy servers, a file cache.

Proxies come from the usual environment variables (https_proxy etc.), which urllib honours.
"""
import http.client
import time
import urllib.error
import urllib.request

from . import HOMEPAGE, SOURCE_NAMES, __version__
from .cache import Cache

USER_AGENT = f"GhostTown/{__version__} (+{HOMEPAGE})"
RETRIES = 1
RETRY_WAIT_S = 30


class SourceError(Exception):
    """A source couldn't be fetched or read. The message is one plain sentence."""


def urllib_transport(url, data, headers, timeout):
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


class Net:
    def __init__(self, cache_dir, *, fresh=False, transport=None, sleep=time.sleep, max_age_days=30):
        self.cache = Cache(cache_dir, max_age_days=max_age_days)
        self.fresh = fresh
        self.transport = transport or urllib_transport
        self.sleep = sleep

    def get(self, url, *, source, data=None, check=None, timeout=120):
        key = url if data is None else url + "\n" + data.decode("utf-8", "replace")
        if not self.fresh:
            body = self.cache.read(source, key)
            if body is not None:
                return body
        name = SOURCE_NAMES.get(source, source)
        problem = f"{name} couldn't be reached"
        for attempt in range(RETRIES + 1):
            if attempt:
                self.sleep(RETRY_WAIT_S)
            try:
                status, body = self.transport(url, data, {"User-Agent": USER_AGENT}, timeout)
            except (OSError, http.client.HTTPException) as e:
                problem = f"{name} couldn't be reached ({e})"
                continue
            if status == 200:
                if check is not None:
                    check(body)
                self.cache.write(source, key, body)
                return body
            problem = f"{name} answered HTTP {status}"
            if status != 429 and status < 500:
                break
        raise SourceError(problem + "; try again in a minute.")
