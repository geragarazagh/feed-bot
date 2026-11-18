"""Entry point of the service: the bot, the poller, the sender and the status loop in one asyncio process."""

from __future__ import annotations

import asyncio
import logging
import time

from . import __version__, config
from .api import Api
from .bot import Bot
from .poller import Poller, Sender
from .status import Status, sd_notify
from .store import Store
from .web import WebView

log = logging.getLogger("tgfeed")


async def main() -> None:
    cfg = config.load()
    store = Store(cfg.state_dir / "feed.db")
    status = Status(cfg, store)
    api = Api(cfg.bot_token, cfg.ipv6_only)
    web = WebView(ipv6_only=cfg.ipv6_only)
    sender = Sender(api, store, status)
    poller = Poller(cfg, store, web, sender, status)
    bot = Bot(cfg, store, api, web, sender, poller, status)

    me = await api.call("getMe")
    status.bot_ok_at = time.time()  # the Bot API answers; getUpdates keeps this fresh from here
    await bot.set_profile()
    sd_notify("READY=1")
    log.info("tg-feed %s ready as @%s: %d users, %d channels", __version__, me["username"], store.user_count(), store.active_count())

    tasks = [asyncio.create_task(c) for c in (bot.run(), poller.run(), sender.run(), status.run())]
    done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for task in done:
        if task.exception():
            raise task.exception()
    raise RuntimeError("a main task stopped")  # systemd restarts the service


def run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # its request lines would carry the token
    asyncio.run(main())


if __name__ == "__main__":
    run()
