import http.client

import pytest

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
