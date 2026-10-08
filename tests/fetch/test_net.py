import email.message
import http.client
import io
import urllib.request
import urllib.response

import pytest

from ghosttown_fetch import net as net_mod
from ghosttown_fetch.net import USER_AGENT, Net, SourceError, Unreadable
from fakes import Transport

URL = "https://example.org/api"


def test_200_is_cached(tmp_path):
    t = Transport((200, b"ok"))
    net = Net(str(tmp_path), transport=t)
    assert net.get(URL, source="osm") == b"ok"
    assert net.get(URL, source="osm") == b"ok"
    assert len(t.calls) == 1


def test_post_data_is_part_of_the_cache_key(tmp_path):
    net = Net(str(tmp_path), transport=Transport((200, b"a"), (200, b"b")))
    assert net.get(URL, source="osm", data=b"q=1") == b"a"
    assert net.get(URL, source="osm", data=b"q=2") == b"b"


def test_sends_an_identifying_user_agent(tmp_path):
    t = Transport((200, b"ok"))
    Net(str(tmp_path), transport=t).get(URL, source="osm")
    assert t.calls[0][2]["User-Agent"] == USER_AGENT
    assert USER_AGENT.startswith("GhostTown/") and "github.com" in USER_AGENT


def test_retries_once_after_429(tmp_path):
    slept = []
    net = Net(str(tmp_path), transport=Transport((429, b""), (200, b"ok")), sleep=slept.append)
    assert net.get(URL, source="osm") == b"ok"
    assert slept == [30]


def test_gives_up_with_one_plain_sentence(tmp_path):
    net = Net(str(tmp_path), transport=Transport((503, b""), (503, b"")), sleep=lambda s: None)
    with pytest.raises(SourceError) as e:
        net.get(URL, source="osm")
    msg = str(e.value)
    assert "OpenStreetMap" in msg and "503" in msg and msg.endswith(".")


def test_does_not_retry_a_404(tmp_path):
    t = Transport((404, b""))
    with pytest.raises(SourceError):
        Net(str(tmp_path), transport=t, sleep=lambda s: None).get(URL, source="osm")
    assert len(t.calls) == 1


def test_network_errors_become_source_errors(tmp_path):
    t = Transport(OSError("no route to host"), OSError("no route to host"))
    with pytest.raises(SourceError, match="couldn't be reached"):
        Net(str(tmp_path), transport=t, sleep=lambda s: None).get(URL, source="osm")


def test_a_rejected_answer_is_not_cached(tmp_path):
    def check(body):
        if body == b"bad":
            raise SourceError("The answer was incomplete.")

    net = Net(str(tmp_path), transport=Transport((200, b"bad"), (200, b"good")))
    with pytest.raises(SourceError, match="incomplete"):
        net.get(URL, source="osm", check=check)
    assert net.get(URL, source="osm", check=check) == b"good"


def test_fresh_skips_cached_answers_but_refreshes_them(tmp_path):
    Net(str(tmp_path), transport=Transport((200, b"old"))).get(URL, source="osm")
    assert Net(str(tmp_path), fresh=True, transport=Transport((200, b"new"))).get(URL, source="osm") == b"new"
    assert Net(str(tmp_path), transport=Transport()).get(URL, source="osm") == b"new"


def test_a_damaged_cache_entry_is_fetched_again(tmp_path):
    def check(body):
        if body != b"good":
            raise SourceError("The answer was damaged.")

    t = Transport((200, b"good"), (200, b"good"))
    net = Net(str(tmp_path), transport=t)
    assert net.get(URL, source="osm", check=check) == b"good"
    entry, = (tmp_path / "osm").iterdir()
    entry.write_bytes(b"trunc")  # the stored answer is damaged on disk
    assert net.get(URL, source="osm", check=check) == b"good" and len(t.calls) == 2
    assert entry.read_bytes() == b"good"


def test_a_one_off_download_skips_the_response_cache(tmp_path):
    t = Transport((200, b"big"), (200, b"big"))
    net = Net(str(tmp_path), transport=t)
    assert net.get(URL, source="toronto", keep=False) == b"big"
    assert not (tmp_path / "toronto").exists()
    assert net.get(URL, source="toronto", keep=False) == b"big" and len(t.calls) == 2


def _readable(body):
    if body != b"good":
        raise Unreadable("The answer couldn't be read.")


def test_an_unreadable_answer_is_asked_for_once_more(tmp_path):
    slept, t = [], Transport((200, b"null"), (200, b"good"))
    assert Net(str(tmp_path), transport=t, sleep=slept.append).get(URL, source="osm", check=_readable) == b"good"
    assert len(t.calls) == 2 and slept == [30]


def test_a_second_unreadable_answer_gives_up_and_stores_nothing(tmp_path):
    t = Transport((200, b"null"), (200, b"<html>busy</html>"))
    with pytest.raises(SourceError, match="couldn't be read"):
        Net(str(tmp_path), transport=t, sleep=lambda s: None).get(URL, source="osm", check=_readable)
    assert len(t.calls) == 2 and not (tmp_path / "osm").exists()


def test_a_refusal_that_asking_again_wont_change_is_final(tmp_path):
    def check(body):
        raise SourceError("There is no data here.")  # like "Ontario has no LiDAR here"

    t = Transport((200, b"empty"), (200, b"empty"))
    with pytest.raises(SourceError, match="no data here"):
        Net(str(tmp_path), transport=t, sleep=lambda s: None).get(URL, source="osm", check=check)
    assert len(t.calls) == 1


def test_an_answer_cut_off_twice_says_so_in_plain_words(tmp_path):
    cut = http.client.IncompleteRead(b"x" * 10, 90)
    with pytest.raises(SourceError) as e:
        Net(str(tmp_path), transport=Transport(cut, cut), sleep=lambda s: None).get(URL, source="nrcan")
    assert str(e.value) == "Natural Resources Canada sent an answer that was cut off; try again in a minute."


def test_headers_are_sent_but_not_part_of_the_cache_key(tmp_path):
    t = Transport((200, b"ok"))
    net = Net(str(tmp_path), transport=t)
    assert net.get(URL, source="osm", headers={"Authorization": "OAuth secret"}) == b"ok"
    assert t.calls[0][2]["Authorization"] == "OAuth secret" and t.calls[0][2]["User-Agent"] == USER_AGENT
    assert net.get(URL, source="osm", headers={"Authorization": "OAuth other"}) == b"ok"
    assert len(t.calls) == 1
    for entry in (tmp_path / "osm").iterdir():   # names are hashes of the key; the body is what could leak
        assert b"secret" not in entry.read_bytes()


def test_a_key_replaces_the_url_as_cache_key(tmp_path):
    t = Transport((200, b"img"))
    net = Net(str(tmp_path), transport=t)
    assert net.get("https://cdn.example/a?sig=1", source="osm", key="photo:7") == b"img"
    assert net.get("https://cdn.example/a?sig=2", source="osm", key="photo:7") == b"img"
    assert len(t.calls) == 1


def test_cached_reads_a_stored_answer_by_key(tmp_path):
    net = Net(str(tmp_path), transport=Transport((200, b"img")))
    assert net.cached("osm", "photo:7") is None
    net.get("https://cdn.example/a?sig=1", source="osm", key="photo:7")
    assert net.cached("osm", "photo:7") == b"img"
    assert Net(str(tmp_path), fresh=True, transport=Transport()).cached("osm", "photo:7") is None


def test_source_errors_carry_the_http_status(tmp_path):
    with pytest.raises(SourceError) as e:
        Net(str(tmp_path), transport=Transport((401, b"")), sleep=lambda s: None).get(URL, source="osm")
    assert e.value.status == 401
    with pytest.raises(SourceError) as e:
        Net(str(tmp_path), transport=Transport(OSError("x"), OSError("x")), sleep=lambda s: None).get(URL, source="osm")
    assert e.value.status is None


def test_a_failed_answer_keeps_its_body_but_never_says_it(tmp_path):
    body = b'{"error": {"message": "Invalid OAuth access token made-up-token", "code": 190}}' + b" " * 3000
    with pytest.raises(SourceError) as e:
        Net(str(tmp_path), transport=Transport((401, body)), sleep=lambda s: None).get(URL, source="mapillary")
    assert e.value.body == body[:2048] and "made-up" not in str(e.value)
    assert not (tmp_path / "mapillary").exists()   # failed answers are never stored


def test_when_nothing_answered_there_is_no_body(tmp_path):
    away = Transport(OSError("timed out"), OSError("timed out"))
    with pytest.raises(SourceError) as e:
        Net(str(tmp_path), transport=away, sleep=lambda s: None).get(URL, source="osm")
    assert e.value.status is None and e.value.body is None


def test_a_redirect_that_comes_back_is_a_failed_request_not_retried(tmp_path):
    t = Transport((302, b""))
    with pytest.raises(SourceError) as e:
        Net(str(tmp_path), transport=t, sleep=lambda s: None).get(URL, source="mapillary",
                                                                  headers={"Authorization": "OAuth made-up-token"})
    assert e.value.status == 302 and len(t.calls) == 1


def _servers(redirect_to):
    """urllib handlers standing in for the internet: graph.mapillary.com answers with a 302 to `redirect_to`, every
    other host with 200. Returns (handlers, the requests they saw as (host, scheme, Authorization))."""
    seen = []

    def answer(req, code, location=None):
        seen.append((req.host, req.type, req.get_header("Authorization")))
        headers = email.message.Message()
        if location:
            headers["Location"] = location
        resp = urllib.response.addinfourl(io.BytesIO(b"{}"), headers, req.full_url, code=code)
        resp.msg = "Found" if location else "OK"
        return resp

    class Https(urllib.request.HTTPSHandler):
        def https_open(self, req):
            return answer(req, 302, redirect_to) if req.host == "graph.mapillary.com" else answer(req, 200)

    class Http(urllib.request.HTTPHandler):
        def http_open(self, req):
            return answer(req, 200)

    return (Https, Http), seen


@pytest.mark.parametrize("target", ["https://scontent.example.fbcdn.net/x.jpg", "http://graph.mapillary.com/images"],
                         ids=["another host", "plain http"])
def test_a_request_with_credentials_does_not_follow_a_redirect(monkeypatch, target):
    handlers, seen = _servers(target)
    monkeypatch.setattr(net_mod, "_OPENER", net_mod.opener(*handlers))
    status, _body = net_mod.urllib_transport("https://graph.mapillary.com/images?bbox=1,2,3,4", None,
                                             {"User-Agent": USER_AGENT, "Authorization": "OAuth made-up-token"}, 10)
    assert status == 302 and seen == [("graph.mapillary.com", "https", "OAuth made-up-token")]


def test_a_request_without_credentials_still_follows_a_redirect(monkeypatch):
    handlers, seen = _servers("https://scontent.example.fbcdn.net/x.jpg")
    monkeypatch.setattr(net_mod, "_OPENER", net_mod.opener(*handlers))
    status, _body = net_mod.urllib_transport("https://graph.mapillary.com/x", None, {"User-Agent": USER_AGENT}, 10)
    assert status == 200 and [host for host, _scheme, _auth in seen] == ["graph.mapillary.com",
                                                                         "scontent.example.fbcdn.net"]
