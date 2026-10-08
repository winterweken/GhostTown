"""HTTP for every source: identifying User-Agent, one retry for busy servers and unreadable answers, a file cache.
A request carrying credentials never follows a redirect, so they reach only the host they were meant for.

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
ERROR_BODY_BYTES = 2048   # of a failed answer, kept on its SourceError


class SourceError(Exception):
    """A source couldn't be fetched or read. The message is one plain sentence; `status` is the last HTTP
    status when a server answered, else None, and `body` the start of that answer (None when nothing answered),
    for callers that tell one refusal from another by it. The body never goes into the message: a server may
    quote the credentials back."""

    def __init__(self, message, status=None, body=None):
        super().__init__(message)
        self.status = status
        self.body = body


class Unreadable(SourceError):
    """An answer came through but can't be read, like NRCan's `null`; asking once more may get a good one."""


class _NoRedirectWithCredentials(urllib.request.HTTPRedirectHandler):
    """Redirects are followed, except for a request that carries Authorization: urllib would copy the header to
    wherever the redirect points, another host or plain http. That redirect comes back as its 30x answer instead,
    a failed request."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if req.has_header("Authorization"):
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def opener(*handlers):
    """urllib's opener (proxies from the environment, HTTPS) with the redirect rule above; `handlers` are for
    tests that stand in for servers."""
    return urllib.request.build_opener(_NoRedirectWithCredentials, *handlers)


_OPENER = opener()


def urllib_transport(url, data, headers, timeout):
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        with _OPENER.open(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def _still_good(body, check):
    """A stored answer is used only while it passes the source's check. One damaged on disk (or
    written by a version with a looser check) is fetched again instead of failing every build."""
    if check is None:
        return True
    try:
        check(body)
    except SourceError:
        return False
    return True


class Net:
    def __init__(self, cache_dir, *, fresh=False, transport=None, sleep=time.sleep, max_age_days=30):
        self.cache = Cache(cache_dir, max_age_days=max_age_days)
        self.fresh = fresh
        self.transport = transport or urllib_transport
        self.sleep = sleep

    def get(self, url, *, source, data=None, check=None, timeout=120, keep=True, headers=None, key=None):
        """The answer's bytes. keep=False is for one-off downloads, like the City's 81 MB massing model,
        that skip the response cache because their caller keeps its own copy, and for answers that go
        stale, like signed links. `headers` are sent but never part of the cache key. `key` replaces the
        URL as the cache key, for answers whose URL changes (signed links)."""
        if key is None:
            key = url if data is None else url + "\n" + data.decode("utf-8", "replace")
        if keep and not self.fresh:
            body = self.cache.read(source, key)
            if body is not None and _still_good(body, check):
                return body
        name = SOURCE_NAMES.get(source, source)
        problem, status, answer = f"{name} couldn't be reached", None, None
        send = {"User-Agent": USER_AGENT, **(headers or {})}
        for attempt in range(RETRIES + 1):
            if attempt:
                self.sleep(RETRY_WAIT_S)
            try:
                status, body = self.transport(url, data, send, timeout)
            except http.client.IncompleteRead:
                problem, status, answer = f"{name} sent an answer that was cut off", None, None
                continue
            except (OSError, http.client.HTTPException) as e:
                problem, status, answer = f"{name} couldn't be reached ({e})", None, None
                continue
            if status == 200:
                if check is not None:
                    try:
                        check(body)
                    except Unreadable:
                        if attempt < RETRIES:
                            continue
                        raise
                if keep:
                    self.cache.write(source, key, body)
                return body
            problem, answer = f"{name} answered HTTP {status}", body[:ERROR_BODY_BYTES]
            if status != 429 and status < 500:
                break
        raise SourceError(problem + "; try again in a minute.", status=status, body=answer)

    def prune(self, source):
        """Delete `source`'s stored answers once they are older than the cache's age, so they don't stay on disk."""
        self.cache.prune(source)

    def cached(self, source, key, check=None):
        """A stored answer by cache key, or None (also when fresh, expired or failing its check)."""
        if self.fresh:
            return None
        body = self.cache.read(source, key)
        return body if body is not None and _still_good(body, check) else None
