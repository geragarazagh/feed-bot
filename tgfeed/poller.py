"""Reading the channels and delivering their new posts.

The Poller reads each distinct channel once for all its readers, often while the channel is
active and rarely while it is quiet, and hands every new post to the Sender as a card: the
post's t.me link with Telegram's large preview above it. The Sender keeps Telegram's limits
(about one message a second per chat, under 30 a second overall) and forgets a user who blocked
the bot.
"""

from __future__ import annotations

import asyncio
import heapq
import itertools
import logging
import random
import time
from dataclasses import dataclass

import httpx

from .api import Api, ApiError
from .config import Config
from .status import Status
from .store import Store
from .texts import t
from .web import PAGE, NotReadable, Post, WebView

log = logging.getLogger("tgfeed.poller")

TICK = 10  # seconds between two looks at which channels are due
GAP = 0.3  # seconds between two reads in a round
MAX_PAGES = 3  # pages (of 20 posts) read per channel per round; a longer backlog goes on next round
STRIKES = 3  # web view redirects in a row before a channel is taken as closed


def card(link: str) -> dict:
    """A post as the bot sends it: the link, with the post's preview as a large card above it."""
    return {
        "text": link,
        "link_preview_options": {"url": link, "prefer_large_media": True, "show_above_text": True},
    }


@dataclass(order=True)
class _Item:
    ready_at: float
    seq: int
    chat_id: int = 0
    params: dict | None = None
    tries: int = 0
    is_post: bool = False


class Sender:
    PER_CHAT = 1.05  # seconds between two messages to one chat
    GLOBAL = 1 / 25  # seconds between any two messages

    def __init__(self, api: Api, store: Store, status: Status):
        self.api = api
        self.store = store
        self.status = status
        self._heap: list[_Item] = []
        self._seq = itertools.count()
        self._next_for: dict[int, float] = {}
        self._wake = asyncio.Event()

    def post(self, chat_id: int, link: str, silent: bool) -> None:
        self.put(chat_id, {**card(link), "disable_notification": silent or None}, is_post=True)

    def put(self, chat_id: int, params: dict, is_post: bool = False) -> None:
        heapq.heappush(self._heap, _Item(time.monotonic(), next(self._seq), chat_id, params, 0, is_post))
        self._wake.set()

    @property
    def backlog(self) -> int:
        return len(self._heap)

    async def run(self) -> None:
        while True:
            if not self._heap:
                self._wake.clear()
                await self._wake.wait()
                continue
            item = heapq.heappop(self._heap)
            now = time.monotonic()
            ready = max(item.ready_at, self._next_for.get(item.chat_id, 0))
            if ready > now:
                item.ready_at = ready
                heapq.heappush(self._heap, item)
                # Sleep until it is due, or until something new arrives that may be due sooner.
                self._wake.clear()
                try:
                    await asyncio.wait_for(self._wake.wait(), timeout=ready - now)
                except asyncio.TimeoutError:
                    pass
                continue
            self._next_for[item.chat_id] = now + self.PER_CHAT
            await self._send(item)
            await asyncio.sleep(self.GLOBAL)

    async def _send(self, item: _Item) -> None:
        try:
            await self.api.call("sendMessage", chat_id=item.chat_id, **item.params)
            if item.is_post:
                self.store.count(sent=1)
                self.status.last_delivery_at = time.time()
        except ApiError as exc:
            if exc.user_gone:
                self.store.wipe_user(item.chat_id)
                self._drop_chat(item.chat_id)
                log.info("a user blocked the bot: forgotten")
            elif exc.not_started:
                pass  # added by the admin tool before pressing Start: nothing can reach them yet
            elif exc.code == 429 and item.tries < 3:
                item.tries += 1
                item.ready_at = time.monotonic() + (exc.retry_after or 5)
                heapq.heappush(self._heap, item)
            else:
                self.status.error(f"send: {exc.code} {exc.description}")
                log.warning("send failed: %s %s", exc.code, exc.description)
        except (httpx.HTTPError, OSError) as exc:
            if item.tries < 3:
                item.tries += 1
                item.ready_at = time.monotonic() + 30
                heapq.heappush(self._heap, item)
            else:
                self.status.error(f"send: {type(exc).__name__}")

    def _drop_chat(self, chat_id: int) -> None:
        self._heap = [i for i in self._heap if i.chat_id != chat_id]
        heapq.heapify(self._heap)


class Poller:
    def __init__(self, cfg: Config, store: Store, web: WebView, sender: Sender, status: Status):
        self.cfg = cfg
        self.store = store
        self.web = web
        self.sender = sender
        self.status = status
        now = time.time()
        # After a restart the channels are spread over the next interval instead of read at once.
        self.polled: dict[str, float] = {
            c.username: now - random.uniform(0, c.interval) for c in store.channels(queued=False)
        }
        self._strikes: dict[str, int] = {}
        self.wake = asyncio.Event()

    def interval(self, last_post_at: int, now: float) -> int:
        return self.cfg.fast_interval if now - last_post_at < self.cfg.active_window else self.cfg.slow_interval

    async def run(self) -> None:
        while True:
            try:
                await self._round()
                await self._promote()
            except Exception as exc:  # one bad round must not stop the feed
                self.status.error(f"round: {type(exc).__name__}: {exc}")
                log.exception("round crashed")
            self.status.last_poll_at = time.time()
            self.store.prune()
            try:
                await asyncio.wait_for(self.wake.wait(), timeout=TICK)
            except asyncio.TimeoutError:
                pass
            self.wake.clear()

    async def _round(self) -> None:
        now = time.time()
        due = [
            c
            for c in self.store.channels(queued=False)
            if now - self.polled.get(c.username, 0) >= self.interval(c.last_post_at, now)
        ]
        fresh: list[tuple[str, Post]] = []
        polls = 0
        for c in due:
            got, n = await self._read(c.username, c.last_id)
            polls += n
            fresh += [(c.username, p) for p in got]
            await asyncio.sleep(GAP)
        if polls:
            self.store.count(polls=polls)
        # All channels' new posts go out in the order they were published.
        fresh.sort(key=lambda x: (x[1].date, x[0], x[1].link_id))
        users = {}
        for username, post in fresh:
            if not post.service:
                for sub in self.store.readers(username):
                    if post.link_id > sub.since_id:
                        user = users.get(sub.user_id) or users.setdefault(sub.user_id, self.store.user(sub.user_id))
                        if user:
                            self.sender.post(sub.user_id, f"https://t.me/{username}/{post.link_id}", user.silent)
        if fresh:
            log.info("round: %d reads, %d new posts, %d in the send queue", polls, len(fresh), self.sender.backlog)

    async def _read(self, username: str, last_id: int) -> tuple[list[Post], int]:
        """New posts of one channel; advances its mark. Returns (posts, requests made)."""
        new: list[Post] = []
        requests = 0
        full = False
        try:
            for _ in range(MAX_PAGES):
                page = await self.web.newer(username, last_id)
                requests += 1
                page = [p for p in page if p.last_id > last_id]
                if not page:
                    full = False
                    break
                new += page
                last_id = max(p.last_id for p in page)
                full = len(page) >= PAGE
                if not full:
                    break
            self._strikes.pop(username, None)
        except NotReadable:
            self._strikes[username] = self._strikes.get(username, 0) + 1
            if self._strikes[username] >= STRIKES:
                await self._closed(username)
            return [], requests + 1
        except (httpx.HTTPError, ValueError) as exc:
            self.status.error(f"read @{username}: {type(exc).__name__}")
            log.warning("read @%s: %s: %s", username, type(exc).__name__, exc)
            return [], requests + 1
        now = time.time()
        newest = max((p.date for p in new), default=None)
        channel = self.store.channel(username)
        last_post_at = max(newest or 0, channel.last_post_at if channel else 0)
        self.store.advance(username, last_id, newest, self.interval(last_post_at, now))
        # A backlog longer than MAX_PAGES pages is read on in the next round, not after an interval.
        self.polled[username] = 0 if full else now
        return new, requests

    async def _closed(self, username: str) -> None:
        """The web view stopped showing a channel: tell its readers once and drop it."""
        self._strikes.pop(username, None)
        self.polled.pop(username, None)
        for user_id in self.store.drop_channel(username):
            user = self.store.user(user_id)
            if user:
                self.sender.put(user_id, {"text": t("web_off_removed", user.lang, c=f"@{username}")})
        log.info("a channel's web view went off: dropped")

    async def _promote(self) -> None:
        """Start queued channels while there is room under the cap."""
        while self.store.active_count() < self.cfg.max_channels:
            queued = self.store.channels(queued=True)
            if not queued:
                return
            username = queued[0].username
            try:
                ch = await self.web.channel(username)
            except NotReadable:
                await self._closed(username)
                continue
            except httpx.HTTPError:
                return
            newest = max((p.last_id for p in ch.posts), default=0)
            last_date = max((p.date for p in ch.posts), default=0)
            self.store.unqueue(username, newest, last_date)
            self.polled[username] = time.time()
            posts = [p for p in ch.posts if not p.service]
            for sub in self.store.readers(username):
                user = self.store.user(sub.user_id)
                if user is None:
                    continue
                if posts:
                    self.sender.post(sub.user_id, f"https://t.me/{username}/{posts[-1].link_id}", user.silent)
                self.sender.put(
                    sub.user_id,
                    {"text": t("added_one", user.lang, t=ch.title), "link_preview_options": {"is_disabled": True}},
                )
            log.info("a queued channel started")
