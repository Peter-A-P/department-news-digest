"""robots.txt, fetched once per host per run and obeyed.

PLAN.md section 2.2: no ignoring robots rules. This applies to article extraction above
all, where the request is for a page a publisher may not want read by a machine. A feed
the publisher advertises is a different thing, but the rules are checked for both, and a
host whose robots.txt cannot be read is treated as allowing nothing rather than
everything: the cautious default is the one that cannot embarrass anybody.
"""

from __future__ import annotations

from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from clippings.constants import USER_AGENT

# The product token a publisher would write in their robots.txt to address this project.
AGENT_TOKEN = "clippings"


class RobotsCache:
    """One robots.txt per host, fetched at most once per run."""

    def __init__(self, client: httpx.Client, *, default_allow: bool = False) -> None:
        self._client = client
        self._parsers: dict[str, RobotFileParser | None] = {}
        # What to do when robots.txt cannot be fetched or parsed. False by default: a host
        # that will not tell us is not asked again.
        self._default_allow = default_allow

    def _parser(self, host_root: str) -> RobotFileParser | None:
        if host_root in self._parsers:
            return self._parsers[host_root]
        parser: RobotFileParser | None = None
        try:
            response = self._client.get(f"{host_root}/robots.txt")
            if response.status_code == 404:
                # No robots.txt is an explicit absence of restrictions, which every crawler
                # in existence reads as permission.
                parser = RobotFileParser()
                parser.parse([])
            elif response.is_success:
                parser = RobotFileParser()
                parser.parse(response.text.splitlines())
        except httpx.HTTPError:
            parser = None
        self._parsers[host_root] = parser
        return parser

    def allows(self, url: str) -> bool:
        """Whether this project may fetch `url`."""
        parts = urlsplit(url)
        if not parts.scheme or not parts.netloc:
            return False
        host_root = f"{parts.scheme}://{parts.netloc}"
        parser = self._parser(host_root)
        if parser is None:
            return self._default_allow
        path = parts.path or "/"
        if parts.query:
            path = f"{path}?{parts.query}"
        # Checked under both the product token and the full user agent string, because
        # publishers write either.
        return parser.can_fetch(AGENT_TOKEN, path) and parser.can_fetch(USER_AGENT, path)

    def crawl_delay(self, url: str) -> float | None:
        parts = urlsplit(url)
        parser = self._parser(f"{parts.scheme}://{parts.netloc}")
        if parser is None:
            return None
        delay = parser.crawl_delay(AGENT_TOKEN)
        return float(delay) if delay is not None else None


class AllowAll(RobotsCache):
    """For tests and for offline runs over fixtures, where nothing is fetched."""

    # Deliberately does not call super().__init__: there is no client to hold.
    def __init__(self) -> None:
        self._parsers = {}
        self._default_allow = True

    def allows(self, url: str) -> bool:
        return True

    def crawl_delay(self, url: str) -> float | None:
        return None
