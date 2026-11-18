"""State on disk (SQLite). Kept on purpose to the minimum the bot needs:

- users: Telegram id, language, flags (language chosen by hand, silent);
- subs: which channel usernames a user reads, paused or not, and the post the subscription
  starts after (so a post shown on /add is not sent again by the next poll);
- channels: per username, the newest post seen, when the channel last posted, how often it is
  polled, and whether it waits in the queue;
- counts: messages sent and polls made per hour, numbers only (for status and egress).

No post content, no message logs, no names of people.
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id         INTEGER PRIMARY KEY,
    lang       TEXT NOT NULL DEFAULT 'en',
    lang_fixed INTEGER NOT NULL DEFAULT 0,  -- 1: chosen in /settings, no longer follows the app
    silent     INTEGER NOT NULL DEFAULT 0   -- 1: posts arrive without sound
);
CREATE TABLE IF NOT EXISTS channels (
    username     TEXT PRIMARY KEY,           -- lower case, no @
    last_id      INTEGER NOT NULL DEFAULT 0, -- newest post id seen (an album's last part)
    last_post_at INTEGER NOT NULL DEFAULT 0, -- unix time of the newest post
    interval     INTEGER NOT NULL DEFAULT 300,
    queued_at    INTEGER                     -- not NULL: waits for a free place under the cap
);
CREATE TABLE IF NOT EXISTS subs (
    user_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    channel  TEXT NOT NULL REFERENCES channels(username),
    paused   INTEGER NOT NULL DEFAULT 0,
    since_id INTEGER NOT NULL DEFAULT 0,     -- posts up to this id are not sent to this user
    PRIMARY KEY (user_id, channel)
);
CREATE TABLE IF NOT EXISTS counts (
    hour  INTEGER PRIMARY KEY,               -- unix time // 3600
    sent  INTEGER NOT NULL DEFAULT 0,
    polls INTEGER NOT NULL DEFAULT 0
);
"""


@dataclass(frozen=True)
class User:
    id: int
    lang: str
    lang_fixed: bool
    silent: bool


@dataclass(frozen=True)
class Channel:
    username: str
    last_id: int
    last_post_at: int
    interval: int
    queued_at: int | None


@dataclass(frozen=True)
class Sub:
    user_id: int
    channel: str
    paused: bool
    since_id: int


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, isolation_level=None, timeout=10)  # autocommit
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript(SCHEMA)

    # users ----------------------------------------------------------------------------------
    def user(self, user_id: int) -> User | None:
        row = self.db.execute("SELECT id, lang, lang_fixed, silent FROM users WHERE id=?", (user_id,)).fetchone()
        return User(row[0], row[1], bool(row[2]), bool(row[3])) if row else None

    def touch_user(self, user_id: int, app_lang: str | None) -> User:
        """Create the user on first contact; follow the app's language until one is chosen by hand."""
        self.db.execute("INSERT OR IGNORE INTO users (id, lang) VALUES (?, ?)", (user_id, app_lang or "en"))
        if app_lang:
            self.db.execute("UPDATE users SET lang=? WHERE id=? AND lang_fixed=0", (app_lang, user_id))
        return self.user(user_id)

    def set_lang(self, user_id: int, lang: str) -> None:
        self.db.execute("UPDATE users SET lang=?, lang_fixed=1 WHERE id=?", (lang, user_id))

    def set_silent(self, user_id: int, silent: bool) -> None:
        self.db.execute("UPDATE users SET silent=? WHERE id=?", (int(silent), user_id))

    def wipe_user(self, user_id: int) -> None:
        """Forget a user entirely; channels nobody reads any more go too."""
        self.db.execute("DELETE FROM subs WHERE user_id=?", (user_id,))
        self.db.execute("DELETE FROM users WHERE id=?", (user_id,))
        self.drop_orphans()

    def user_count(self) -> int:
        return self.db.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    # channels -------------------------------------------------------------------------------
    def channel(self, username: str) -> Channel | None:
        row = self.db.execute(
            "SELECT username, last_id, last_post_at, interval, queued_at FROM channels WHERE username=?", (username,)
        ).fetchone()
        return Channel(*row) if row else None

    def channels(self, queued: bool | None = None) -> list[Channel]:
        sql = "SELECT username, last_id, last_post_at, interval, queued_at FROM channels"
        if queued is True:
            sql += " WHERE queued_at IS NOT NULL ORDER BY queued_at, username"
        elif queued is False:
            sql += " WHERE queued_at IS NULL ORDER BY username"
        else:
            sql += " ORDER BY username"
        return [Channel(*row) for row in self.db.execute(sql)]

    def active_count(self) -> int:
        return self.db.execute("SELECT COUNT(*) FROM channels WHERE queued_at IS NULL").fetchone()[0]

    def add_channel(self, username: str, last_id: int, last_post_at: int, interval: int, queued: bool) -> None:
        self.db.execute(
            "INSERT OR IGNORE INTO channels (username, last_id, last_post_at, interval, queued_at) VALUES (?,?,?,?,?)",
            (username, last_id, last_post_at, interval, int(time.time()) if queued else None),
        )

    def advance(self, username: str, last_id: int, last_post_at: int | None, interval: int) -> None:
        self.db.execute(
            "UPDATE channels SET last_id=MAX(last_id, ?), last_post_at=MAX(last_post_at, ?), interval=? WHERE username=?",
            (last_id, last_post_at or 0, interval, username),
        )

    def unqueue(self, username: str, last_id: int, last_post_at: int) -> None:
        self.db.execute(
            "UPDATE channels SET queued_at=NULL, last_id=?, last_post_at=? WHERE username=?",
            (last_id, last_post_at, username),
        )

    def drop_channel(self, username: str) -> list[int]:
        """Remove a channel for everyone; returns the users who had it."""
        users = [r[0] for r in self.db.execute("SELECT user_id FROM subs WHERE channel=?", (username,))]
        self.db.execute("DELETE FROM subs WHERE channel=?", (username,))
        self.db.execute("DELETE FROM channels WHERE username=?", (username,))
        return users

    def drop_orphans(self) -> int:
        return self.db.execute(
            "DELETE FROM channels WHERE username NOT IN (SELECT DISTINCT channel FROM subs)"
        ).rowcount

    # subscriptions --------------------------------------------------------------------------
    def subs_of(self, user_id: int) -> list[Sub]:
        rows = self.db.execute(
            "SELECT user_id, channel, paused, since_id FROM subs WHERE user_id=? ORDER BY rowid", (user_id,)
        )
        return [Sub(r[0], r[1], bool(r[2]), r[3]) for r in rows]

    def readers(self, channel: str) -> list[Sub]:
        """Subscriptions that should get this channel's posts (paused ones left out)."""
        rows = self.db.execute(
            "SELECT user_id, channel, paused, since_id FROM subs WHERE channel=? AND paused=0", (channel,)
        )
        return [Sub(r[0], r[1], bool(r[2]), r[3]) for r in rows]

    def subscribe(self, user_id: int, channel: str, since_id: int) -> bool:
        return self.db.execute(
            "INSERT OR IGNORE INTO subs (user_id, channel, since_id) VALUES (?,?,?)", (user_id, channel, since_id)
        ).rowcount == 1

    def unsubscribe(self, user_id: int, channel: str) -> bool:
        gone = self.db.execute("DELETE FROM subs WHERE user_id=? AND channel=?", (user_id, channel)).rowcount == 1
        self.drop_orphans()
        return gone

    def set_paused(self, user_id: int, channel: str, paused: bool) -> bool:
        return self.db.execute(
            "UPDATE subs SET paused=? WHERE user_id=? AND channel=?", (int(paused), user_id, channel)
        ).rowcount == 1

    def sub_count(self, channel: str) -> int:
        return self.db.execute("SELECT COUNT(*) FROM subs WHERE channel=?", (channel,)).fetchone()[0]

    # counts ---------------------------------------------------------------------------------
    def count(self, sent: int = 0, polls: int = 0) -> None:
        hour = int(time.time()) // 3600
        self.db.execute(
            "INSERT INTO counts (hour, sent, polls) VALUES (?,?,?) "
            "ON CONFLICT(hour) DO UPDATE SET sent=sent+excluded.sent, polls=polls+excluded.polls",
            (hour, sent, polls),
        )

    def counted(self, hours: int = 24) -> tuple[int, int]:
        since = int(time.time()) // 3600 - hours + 1
        row = self.db.execute("SELECT SUM(sent), SUM(polls) FROM counts WHERE hour >= ?", (since,)).fetchone()
        return row[0] or 0, row[1] or 0

    def prune(self, keep_days: int = 31) -> None:
        self.db.execute("DELETE FROM counts WHERE hour < ?", (int(time.time()) // 3600 - keep_days * 24,))
