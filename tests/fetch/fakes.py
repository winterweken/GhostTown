class FakeNet:
    """Stands in for ghosttown_fetch.net.Net: answers by source key, records calls."""

    def __init__(self, answers):
        self.answers = answers
        self.calls = []

    def get(self, url, *, source, data=None, check=None, timeout=120):
        self.calls.append((url, source, data))
        answer = self.answers[source]
        if isinstance(answer, Exception):
            raise answer
        if check is not None:
            check(answer)
        return answer
