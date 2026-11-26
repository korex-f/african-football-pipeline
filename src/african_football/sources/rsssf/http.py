"""
http.py: get RSSSF pages politely, with retries.

RSSSF is an archive that volunteers keep. The site has no robots.txt and no
API. Thus this client follows its own rules (decision 21):

- One request at a time, and a minimum interval between two requests
  (DEFAULT_INTERVAL). The raw store keeps each page, thus the adapter gets
  a page only one time.
- A User-Agent that tells what the client is.
- Retries with longer waits for network errors and server errors (5xx).
  During the project, DNS failures occurred often on the network of the
  developer. A 404 is not retried: the page does not exist.

The pages do not declare a character set. Most are ASCII. Some have
Windows-1252 or Latin-1 characters, for example 'Espérance' in the Tunisia
pages. decode_page() tries UTF-8 first, then Windows-1252, then Latin-1.
Latin-1 can decode all bytes, thus decode_page() never fails.
"""

import time
from collections.abc import Callable
from typing import Optional

import requests

BASE_URL = "https://www.rsssf.org/"

# The minimum time between two requests, in seconds.
DEFAULT_INTERVAL = 3.0

# The waits before the retries, in seconds: five retries after the first
# request, about 8 minutes in total. The network of the project has DNS
# failures that last some minutes. With three retries (about 1 minute), the
# survey of November 2026 lost 2 pages (Ethiopia 2007 and 2008).
RETRY_WAITS = (5.0, 15.0, 45.0, 120.0, 300.0)

TIMEOUT = 30.0

USER_AGENT = (
    "african-football-pipeline/1.2 "
    "(historical football data; one request every few seconds)"
)


class RsssfError(Exception):
    """An RSSSF page could not be read."""


class RsssfPageNotFound(RsssfError):
    """The server gave 404 for an RSSSF page."""


def decode_page(data: bytes) -> str:
    """Give the text of a page that has no declared character set."""
    for encoding in ("utf-8", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


class RsssfHttp:
    """
    Get RSSSF pages, one at a time, with retries.

    session, sleep and clock can be replaced in the tests. Then the tests do
    not use the network and do not wait.
    """

    def __init__(
        self,
        interval: float = DEFAULT_INTERVAL,
        retry_waits: tuple[float, ...] = RETRY_WAITS,
        session: Optional[requests.Session] = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.interval = interval
        self.retry_waits = retry_waits
        self.session = session or requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self._sleep = sleep
        self._clock = clock
        self._last_request: Optional[float] = None
        self.requests_sent = 0

    def get(self, url: str) -> str:
        """Give the text of the page at url.

        Raises RsssfPageNotFound for a 404, and RsssfError when all the
        retries failed.
        """
        last_error: Optional[Exception] = None
        for wait in (0.0, *self.retry_waits):
            if wait:
                self._sleep(wait)
            try:
                return self._get_once(url)
            except RsssfPageNotFound:
                raise
            except (requests.RequestException, RsssfError) as error:
                last_error = error
        raise RsssfError(
            f"{url}: no page after {1 + len(self.retry_waits)} requests"
        ) from last_error

    def _get_once(self, url: str) -> str:
        self._wait_for_interval()
        self.requests_sent += 1
        response = self.session.get(url, timeout=TIMEOUT)
        self._last_request = self._clock()
        if response.status_code == 404:
            raise RsssfPageNotFound(f"{url}: 404")
        if response.status_code >= 500:
            raise RsssfError(f"{url}: server error {response.status_code}")
        response.raise_for_status()
        return decode_page(response.content)

    def _wait_for_interval(self) -> None:
        """Wait until `interval` seconds passed after the last request."""
        if self._last_request is None:
            return
        remaining = self.interval - (self._clock() - self._last_request)
        if remaining > 0:
            self._sleep(remaining)
