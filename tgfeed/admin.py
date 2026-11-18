"""The admin's tool on the server (`sudo -u feedbot feedbot-admin ...`): look at the state, and give a user
channels without Telegram (they start from each channel's latest post; nothing is sent for the past).

  feedbot-admin stats
  feedbot-admin channels
  feedbot-admin user 123456789
  feedbot-admin sub 123456789 [--lang ru] @a t.me/b ...
  feedbot-admin unsub 123456789 @a ...
  feedbot-admin wipe 123456789

The running service picks the changes up on its next round.
"""

from __future__ import annotations

import argparse
import asyncio
import time
from datetime import datetime, timezone

from .config import Config, settings_path, state_dir
from .refs import parse_channel_ref
from .store import Store
from .texts import LANGS
from .web import NotReadable, WebView


def _when(ts: int) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d %H:%M") if ts else "-"


async def _subscribe(store: Store, cap: int, user_id: int, refs: list[str], ipv6_only: bool) -> None:
    web = WebView(ipv6_only=ipv6_only)
    try:
        for ref in refs:
            username = parse_channel_ref(ref)
            if username is None:
                print(f"skip {ref}: not a public username")
                continue
            if any(s.channel == username for s in store.subs_of(user_id)):
                print(f"already @{username}")
                continue
            try:
                ch = await web.channel(username)
            except NotReadable as exc:
                print(f"refused @{username}: {exc.reason}")
                continue
            newest = max((p.last_id for p in ch.posts), default=0)
            last_date = max((p.date for p in ch.posts), default=0)
            if store.channel(username) is None:
                queued = store.active_count() >= cap
                interval = 90 if time.time() - last_date < 7200 else 300
                store.add_channel(username, newest, last_date, interval, queued)
            store.subscribe(user_id, username, since_id=newest)
            state = "queued" if store.channel(username).queued_at else "ok"
            print(f"{state:7} @{username} from post {newest} ({ch.title})")
            await asyncio.sleep(0.5)
    finally:
        await web.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="tg-feed admin tool")
    parser.add_argument("command", choices=["stats", "channels", "user", "sub", "unsub", "wipe"])
    parser.add_argument("user", nargs="?", type=int)
    parser.add_argument("channels", nargs="*")
    parser.add_argument("--lang", choices=LANGS, default="en")
    args = parser.parse_args()

    import json

    settings = json.loads(settings_path().read_text()) if settings_path().exists() else {}
    cap = int(settings.get("max_channels", Config.max_channels))
    store = Store(state_dir(settings) / "feed.db")

    if args.command == "stats":
        sent, polls = store.counted(24)
        print(f"users {store.user_count()}, channels {store.active_count()} of {cap}, "
              f"queued {len(store.channels(queued=True))}, sent 24h {sent}, reads 24h {polls}")
    elif args.command == "channels":
        for c in store.channels():
            q = " queued" if c.queued_at else ""
            print(f"@{c.username:30} readers {store.sub_count(c.username):3} every {c.interval:3}s "
                  f"last {c.last_id:7} at {_when(c.last_post_at)}{q}")
    elif args.user is None:
        parser.error("a user id is needed")
    elif args.command == "user":
        u = store.user(args.user)
        print(u or "no such user")
        for s in store.subs_of(args.user):
            print(f"  @{s.channel}{' (paused)' if s.paused else ''}")
    elif args.command == "sub":
        store.touch_user(args.user, None)
        if args.lang != "en":
            store.set_lang(args.user, args.lang)
            store.db.execute("UPDATE users SET lang_fixed=0 WHERE id=?", (args.user,))  # still follows the app
        asyncio.run(_subscribe(store, cap, args.user, args.channels, bool(settings.get("ipv6_only"))))
    elif args.command == "unsub":
        for ref in args.channels:
            u = parse_channel_ref(ref)
            print(f"{'removed' if u and store.unsubscribe(args.user, u) else 'not listed'} {ref}")
    elif args.command == "wipe":
        store.wipe_user(args.user)
        print("wiped")


if __name__ == "__main__":
    main()
