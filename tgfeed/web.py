"""Reading public channels from Telegram's web view, t.me/s/<channel>, with no Telegram account.

Two requests are used:

- GET  https://t.me/s/<channel>            the channel's page: title and its latest ~20 posts
- POST https://t.me/s/<channel>?after=<id>  the page's "load newer" call (X-Requested-With:
  XMLHttpRequest, empty body): a JSON string with the HTML of up to 20 posts newer than <id>,
  oldest first; `""` (2 bytes) when nothing is new.

An album is one block in the web view: its first post id in `data-post`, every part as a
`?single` link. The bot links to the first id (Telegram previews it as the whole album) and moves
its mark past the last part. Channels whose web view is off answer the GET with a redirect to
t.me/<channel>; that page then tells a channel (subscribers) from a group (members) or a user.
"""

from __future__ import annotations

import asyncio
import html
import json
import re
from dataclasses import dataclass
from datetime import datetime

import httpx

BASE = "https://t.me"
PAGE = 20  # posts per web-view page
# Honest and short: every byte of a request is billable egress on the free VM (a longer browser-like
# User-Agent cost 57 B more per read, measured 2026-11-18).
HEADERS = {"User-Agent": "FeedChannelsBot", "Accept-Encoding": "gzip"}
XHR = {"X-Requested-With": "XMLHttpRequest"}

_POST = re.compile(r'data-post="([A-Za-z0-9_]+)/(\d+)"')
_SINGLE = re.compile(r'href="https://t\.me/[A-Za-z0-9_]+/(\d+)\?single"')
_DATE = re.compile(r'<time datetime="([^"]+)"')
_TITLE = re.compile(r'<div class="tgme_channel_info_header_title"[^>]*>(?:<span[^>]*>)?(.*?)</', re.S)
_PAGE_TITLE = re.compile(r'<div class="tgme_page_title"[^>]*>\s*<span[^>]*>(.*?)</span>', re.S)
_EXTRA = re.compile(r'<div class="tgme_page_extra">([^<]*)')


@dataclass(frozen=True)
class Post:
    link_id: int  # the id a link opens: the post, or an album's first part
    last_id: int  # the newest id inside it: the album's last part
    date: int  # unix seconds
    service: bool  # pinned message, new photo and the like: skipped, never sent


@dataclass(frozen=True)
class Channel:
    username: str  # as the web view spells it (case kept for display)
    title: str
    posts: list[Post]


class NotReadable(Exception):
    """The channel cannot be read from the web view. `reason`: preview_off, group, not_channel."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def parse_posts(markup: str) -> list[Post]:
    """Posts of a web-view page or a "load newer" answer, oldest first."""
    found = list(_POST.finditer(markup))
    posts = []
    for i, m in enumerate(found):
        # The block of one post runs from its data-post to the next one; the wrapper carrying the
        # service class opens just before data-post.
        head = markup[markup.rfind("tgme_widget_message_wrap", 0, m.start()) : m.start()]
        block = markup[m.end() : found[i + 1].start() if i + 1 < len(found) else len(markup)]
        link_id = int(m.group(2))
        ids = [link_id] + [int(x) for x in _SINGLE.findall(block)]
        date = _DATE.search(block)
        posts.append(
            Post(
                link_id=link_id,
                last_id=max(ids),
                date=int(datetime.fromisoformat(date.group(1)).timestamp()) if date else 0,
                service="service_message" in head,
            )
        )
    posts.sort(key=lambda p: p.link_id)
    return posts


def classify(page: str) -> str:
    """What a t.me/<name> page shows when its web view redirects: preview_off, group or not_channel."""
    extra = " ".join(_EXTRA.findall(page)).lower()
    if "subscriber" in extra:
        return "preview_off"
    if "member" in extra:
        return "group"
    return "not_channel"


class WebView:
    def __init__(self, timeout: float = 20.0, ipv6_only: bool = False):
        # One keep-alive connection serves a whole polling round: a TLS handshake costs more
        # egress than a dozen polls.
        self.http = httpx.AsyncClient(
            base_url=BASE,
            headers=HEADERS,
            timeout=timeout,
            follow_redirects=False,
            transport=httpx.AsyncHTTPTransport(
                limits=httpx.Limits(max_connections=2, max_keepalive_connections=2, keepalive_expiry=120),
                local_address="::" if ipv6_only else None,
            ),
        )

    async def close(self) -> None:
        await self.http.aclose()

    async def _request(self, method: str, url: str, **kw) -> httpx.Response:
        """One retry after a dropped connection: t.me may close an idle keep-alive at any moment."""
        try:
            r = await self.http.request(method, url, **kw)
        except httpx.TransportError:
            await asyncio.sleep(1)
            r = await self.http.request(method, url, **kw)
        self.http.cookies.clear()  # t.me sets a session cookie; sending it back costs bytes and serves nothing
        return r

    async def channel(self, username: str) -> Channel:
        """The channel page: title and latest posts. Raises NotReadable."""
        r = await self._request("GET", f"/s/{username}")
        if r.status_code in (301, 302, 303, 307, 308):
            page = await self._request("GET", f"/{username}")
            raise NotReadable(classify(page.text))
        r.raise_for_status()
        text = r.text
        title = _TITLE.search(text) or _PAGE_TITLE.search(text)
        posts = parse_posts(text)
        name = _POST.search(text)
        return Channel(
            username=name.group(1) if name else username,
            title=html.unescape(re.sub(r"<[^>]+>", "", title.group(1))).strip() if title else username,
            posts=posts,
        )

    async def newer(self, username: str, after: int) -> list[Post]:
        """Posts newer than `after`, oldest first, at most one page. Raises NotReadable."""
        r = await self._request("POST", f"/s/{username}", params={"after": after}, headers=XHR)
        if r.status_code in (301, 302, 303, 307, 308):
            raise NotReadable("preview_off")
        r.raise_for_status()
        body = r.text
        if len(body) <= 2:  # "" : nothing new
            return []
        return parse_posts(json.loads(body))
