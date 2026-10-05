import urllib.parse


class FakeNet:
    """Stands in for ghosttown_fetch.net.Net: answers by source key, records calls.

    An answer is bytes, an Exception (raised), or a callable (url, data) -> bytes | Exception."""

    def __init__(self, answers):
        self.answers = answers
        self.calls = []
        self.keeps = []
        self.timeouts = []

    def get(self, url, *, source, data=None, check=None, timeout=120, keep=True):
        self.calls.append((url, source, data))
        self.keeps.append(keep)
        self.timeouts.append(timeout)
        answer = self.answers[source]
        if callable(answer):
            answer = answer(url, data)
        if isinstance(answer, Exception):
            raise answer
        if check is not None:
            check(answer)
        return answer


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
