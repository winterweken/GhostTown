import urllib.parse


class FakeNet:
    """Stands in for ghosttown_fetch.net.Net: answers by source key, records calls.

    An answer is bytes, an Exception (raised), or a callable (url, data) -> bytes | Exception."""

    def __init__(self, answers):
        self.answers = answers
        self.calls = []
        self.keeps = []
        self.timeouts = []
        self.headers = []
        self.requests = []   # (url, headers) of each call, kept together: the pool's threads may interleave
        self.keys = []
        self.ages = []       # max_age_days of each call (None for the cache's own age)
        self.pruned = []
        self.slept = []

    def get(self, url, *, source, data=None, check=None, timeout=120, keep=True, headers=None, key=None,
            max_age_days=None):
        self.calls.append((url, source, data))
        self.keeps.append(keep)
        self.timeouts.append(timeout)
        self.headers.append(dict(headers or {}))
        self.requests.append((url, dict(headers or {})))
        self.keys.append(key)
        self.ages.append(max_age_days)
        answer = self.answers[source]
        if callable(answer):
            answer = answer(url, data)
        if isinstance(answer, Exception):
            raise answer
        if check is not None:
            check(answer)
        return answer

    def cached(self, source, key, check=None):
        return None

    def prune(self, source, max_age_days=None):
        self.pruned.append((source, max_age_days))

    def sleep(self, seconds):
        self.slept.append(seconds)


class Transport:
    """Stands in for net.urllib_transport: hands out (status, body) answers in turn, or raises one."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = []

    def __call__(self, url, data, headers, timeout):
        self.calls.append((url, data, headers))
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def router(table):
    """A FakeNet answer that picks a body by the first key found in the URL or the decoded POSTed form."""
    def answer(url, data):
        text = url + "\n" + (urllib.parse.unquote_plus(data.decode("ascii")) if data else "")
        for key, body in table.items():
            if key in text:
                return body(url, data) if callable(body) else body
        raise AssertionError("no fake answer for " + text[:300])
    return answer


def form(data):
    """The POSTed form of a FakeNet call as a dict."""
    return dict(urllib.parse.parse_qsl(data.decode("ascii")))
