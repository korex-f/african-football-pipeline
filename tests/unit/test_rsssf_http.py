"""
Tests for sources/rsssf/http.py.

A fake session gives the responses, a fake clock gives the time, and a fake
sleep records the waits. Thus the tests do not use the network and do not
wait.
"""

import pytest
import requests

from african_football.sources.rsssf.http import (
    RsssfError,
    RsssfHttp,
    RsssfPageNotFound,
    decode_page,
)


class FakeResponse:
    def __init__(self, status_code: int = 200, content: bytes = b"page"):
        self.status_code = status_code
        self.content = content

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}")


class FakeSession:
    """Gives the results in sequence. An exception in the list is raised."""

    def __init__(self, results: list):
        self.results = list(results)
        self.headers: dict[str, str] = {}
        self.urls: list[str] = []

    def get(self, url: str, timeout: float):
        self.urls.append(url)
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class FakeTime:
    def __init__(self) -> None:
        self.now = 100.0
        self.waits: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.waits.append(seconds)
        self.now += seconds


def _http(session: FakeSession, fake_time: FakeTime, **kwargs) -> RsssfHttp:
    return RsssfHttp(
        session=session,  # pyright: ignore[reportArgumentType]
        sleep=fake_time.sleep,
        clock=fake_time.clock,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# decode_page
# ---------------------------------------------------------------------------


def test_decode_ascii():
    assert decode_page(b"Enyimba 1-0 Rangers") == "Enyimba 1-0 Rangers"


def test_decode_utf8():
    assert decode_page("Espérance".encode("utf-8")) == "Espérance"


def test_decode_windows_1252():
    # 0xe9 is 'é' in Windows-1252 and in Latin-1, and not valid UTF-8.
    assert decode_page(b"Esp\xe9rance") == "Espérance"


def test_decode_never_fails():
    # 0x81 is not a character in Windows-1252. Latin-1 decodes all bytes.
    assert decode_page(b"a\x81b") == "a\x81b"


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------


def test_get_gives_the_text_and_sends_the_user_agent():
    session = FakeSession([FakeResponse(content=b"Nigeria 2015")])
    http = _http(session, FakeTime())

    assert http.get("https://www.rsssf.org/tablesn/nig2015.html") == "Nigeria 2015"
    assert "african-football-pipeline" in session.headers["User-Agent"]


def test_interval_between_two_requests():
    fake_time = FakeTime()
    session = FakeSession([FakeResponse(), FakeResponse()])
    http = _http(session, fake_time, interval=3.0)

    http.get("https://www.rsssf.org/a.html")
    fake_time.now += 1.0  # the caller used 1 second
    http.get("https://www.rsssf.org/b.html")

    assert fake_time.waits == [2.0]


def test_no_wait_when_the_interval_passed():
    fake_time = FakeTime()
    http = _http(FakeSession([FakeResponse(), FakeResponse()]), fake_time, interval=3.0)

    http.get("https://www.rsssf.org/a.html")
    fake_time.now += 10.0
    http.get("https://www.rsssf.org/b.html")

    assert fake_time.waits == []


def test_retry_after_a_network_error():
    fake_time = FakeTime()
    session = FakeSession(
        [requests.ConnectionError("DNS failure"), FakeResponse(content=b"ok")]
    )
    http = _http(session, fake_time, retry_waits=(5.0, 15.0))

    assert http.get("https://www.rsssf.org/a.html") == "ok"
    assert fake_time.waits == [5.0]
    assert http.requests_sent == 2


def test_retry_after_a_server_error():
    session = FakeSession([FakeResponse(503), FakeResponse(content=b"ok")])
    http = _http(session, FakeTime(), retry_waits=(5.0,))

    assert http.get("https://www.rsssf.org/a.html") == "ok"


def test_404_is_not_retried():
    session = FakeSession([FakeResponse(404)])
    http = _http(session, FakeTime(), retry_waits=(5.0, 15.0))

    with pytest.raises(RsssfPageNotFound):
        http.get("https://www.rsssf.org/missing.html")
    assert http.requests_sent == 1


def test_error_after_all_retries():
    errors = [requests.ConnectionError("DNS failure")] * 3
    fake_time = FakeTime()
    http = _http(FakeSession(errors), fake_time, retry_waits=(5.0, 15.0))

    with pytest.raises(RsssfError, match="3 requests") as caught:
        http.get("https://www.rsssf.org/a.html")
    assert isinstance(caught.value.__cause__, requests.ConnectionError)
    assert fake_time.waits == [5.0, 15.0]
