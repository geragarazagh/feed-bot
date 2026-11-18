"""The bot's side: commands, adding channels, the channel list, settings, and the profile texts."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict, deque

import httpx

from .api import Api, ApiError
from .config import Config
from .poller import Poller, Sender, card
from .refs import extract_refs, parse_channel_ref
from .status import Status
from .store import Store, User
from .texts import LANG_NAMES, LANGS, lang_of, quoted, t
from .web import NotReadable, WebView

log = logging.getLogger("tgfeed.bot")

NO_PREVIEW = {"is_disabled": True}
COMMANDS = ("add", "channels", "settings", "help")
RATE = object()  # _check's "too many checks this hour"
LIST_MAX = 50  # channels checked from one list: the checklist stays under Telegram's 100 buttons


class Bot:
    def __init__(self, cfg: Config, store: Store, api: Api, web: WebView, sender: Sender, poller: Poller, status: Status):
        self.cfg = cfg
        self.store = store
        self.api = api
        self.web = web
        self.sender = sender
        self.poller = poller
        self.status = status
        self._adds: dict[int, deque] = defaultdict(deque)  # user -> times of recent adds (memory only)
        self._locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._baskets: dict[tuple[int, int], dict] = {}  # (user, message) -> an open checklist (memory only)
        self._forwards: dict[int, tuple[list, list]] = {}  # user -> forwarded channels waiting to be listed
        self._flush_tasks: dict[int, asyncio.Task] = {}

    # profile --------------------------------------------------------------------------------
    async def set_profile(self) -> None:
        """Name, About, Description and the command menu in each language; only what differs is sent."""
        for lang in ("",) + LANGS:
            code = lang or "en"
            try:
                if (await self.api.call("getMyName", language_code=lang))["name"] != t("name", code):
                    await self.api.call("setMyName", name=t("name", code), language_code=lang)
                if (await self.api.call("getMyShortDescription", language_code=lang))["short_description"] != t("about", code):
                    await self.api.call("setMyShortDescription", short_description=t("about", code), language_code=lang)
                if (await self.api.call("getMyDescription", language_code=lang))["description"] != t("description", code):
                    await self.api.call("setMyDescription", description=t("description", code), language_code=lang)
                commands = [{"command": c, "description": t(f"cmd_{c}", code)} for c in COMMANDS]
                if await self.api.call("getMyCommands", language_code=lang) != commands:
                    await self.api.call("setMyCommands", commands=commands, language_code=lang)
            except ApiError as exc:  # cosmetic; never block the start
                log.warning("profile %s: %s", lang or "default", exc)

    # updates --------------------------------------------------------------------------------
    async def run(self) -> None:
        offset = None
        while True:
            try:
                updates = await self.api.call(
                    "getUpdates",
                    offset=offset,
                    timeout=50,
                    allowed_updates=["message", "callback_query", "my_chat_member"],
                )
            except (ApiError, httpx.HTTPError) as exc:
                self.status.error(f"getUpdates: {exc}")
                log.warning("getUpdates: %s", exc)
                await asyncio.sleep(5)
                continue
            self.status.bot_ok_at = time.time()
            for u in updates:
                offset = u["update_id"] + 1
                asyncio.create_task(self._handle(u))

    async def _handle(self, update: dict) -> None:
        sender = (
            (update.get("message") or {}).get("from")
            or (update.get("callback_query") or {}).get("from")
            or (update.get("my_chat_member") or {}).get("from")
            or {}
        )
        async with self._locks[sender.get("id", 0)]:
            try:
                if "message" in update:
                    await self.on_message(update["message"])
                elif "callback_query" in update:
                    await self.on_button(update["callback_query"])
                elif "my_chat_member" in update:
                    await self.on_member(update["my_chat_member"])
            except ApiError as exc:
                if exc.user_gone:
                    self.store.wipe_user(sender.get("id", 0))
                else:
                    self.status.error(f"update: {exc}")
                    log.warning("update: %s", exc)
            except Exception as exc:
                self.status.error(f"update: {type(exc).__name__}: {exc}")
                log.exception("update crashed")

    async def on_member(self, m: dict) -> None:
        chat, status = m["chat"], m["new_chat_member"]["status"]
        if chat["type"] == "private":
            if status == "kicked":  # "Stop and block": forget the user
                self.store.wipe_user(chat["id"])
                log.info("a user stopped the bot: forgotten")
        elif status in ("member", "administrator"):
            await self.api.call("leaveChat", chat_id=chat["id"])  # the bot works in private chats only

    async def on_message(self, msg: dict) -> None:
        if msg["chat"]["type"] != "private" or "from" not in msg:
            return
        user = self.store.touch_user(msg["from"]["id"], lang_of(msg["from"].get("language_code")))
        chat = msg["chat"]["id"]

        # A pick from the old "Choose a Channel" keyboard (removed 2026-11-18), pressed before it was swept away.
        shared = msg.get("chat_shared")
        if shared:
            username = shared.get("username")
            if username:
                await self.add(chat, user, [username.lower()], [], titles={username.lower(): shared.get("title")})
            else:
                await self.say(chat, t("private", user.lang))
            return

        origin = msg.get("forward_origin")
        if origin:
            names, notes = self._forwards.setdefault(user.id, ([], []))
            username = (origin.get("chat") or {}).get("username") if origin["type"] == "channel" else None
            if username and username.lower() not in names:
                names.append(username.lower())
            elif not username:
                note = t("private" if origin["type"] == "channel" else "not_from_channel", user.lang)
                if note not in notes:
                    notes.append(note)
            task = self._flush_tasks.get(user.id)
            if task:
                task.cancel()
            self._flush_tasks[user.id] = asyncio.create_task(self._flush_forwards(chat, user.id))
            return

        text = (msg.get("text") or msg.get("caption") or "").strip()
        if text.startswith("/"):
            command, _, rest = text.partition(" ")
            command = command[1:].split("@", 1)[0].lower()
            await self.command(chat, user, command, rest.strip())
            return
        names, bad = extract_refs(text)
        if names or bad:
            await self.add(chat, user, names, bad)
        else:
            await self.say(chat, t("add_prompt", user.lang))

    async def command(self, chat: int, user: User, command: str, rest: str) -> None:
        if command == "start":
            # A start link may carry a channel: t.me/FeedChannelsBot?start=<username>
            name = parse_channel_ref(rest) if rest else None
            await self.start(chat, user)
            if name:
                await self.add(chat, user, [name], [])
        elif command == "help":
            await self.say(chat, t("help", user.lang, max=self.cfg.max_subs_per_user))
        elif command == "add":
            names, bad = extract_refs(rest) if rest else ([], [])
            if names or bad:
                await self.add(chat, user, names, bad)
            else:
                await self.say(chat, t("add_prompt", user.lang))
        elif command == "channels":
            await self.show_channels(chat, user)
        elif command == "settings":
            text, markup = self.settings_view(user)
            await self.say(chat, text, reply_markup=markup)
        elif command == "stop":
            await self.say(
                chat,
                t("stop_confirm", user.lang),
                reply_markup={"inline_keyboard": [[
                    {"text": t("btn_stop", user.lang), "callback_data": "S", "style": "danger"},
                    {"text": t("btn_cancel", user.lang), "callback_data": "C"},
                ]]},
            )
        else:
            await self.say(chat, t("help", user.lang, max=self.cfg.max_subs_per_user))

    async def start(self, chat: int, user: User) -> None:
        await self.say(chat, t("start", user.lang))

    async def say(self, chat: int, text: str, **params) -> dict:
        params = self.sender.sweep(chat, {"text": text, "link_preview_options": NO_PREVIEW, **params})
        result = await self.api.call("sendMessage", chat_id=chat, **params)
        self.sender.swept(chat, params)
        return result

    # adding ---------------------------------------------------------------------------------
    def _rate_ok(self, user_id: int) -> bool:
        q = self._adds[user_id]
        while q and time.time() - q[0] > 3600:
            q.popleft()
        return len(q) < self.cfg.max_adds_per_hour

    async def _read_channel(self, username: str):
        """The channel page, retried quietly: a user sees an error only when three tries over ~10 s fail."""
        for attempt in range(3):
            try:
                return await self.web.channel(username)
            except httpx.HTTPError:
                if attempt == 2:
                    raise
                await asyncio.sleep(2 + 3 * attempt)

    def _subscribe(self, user: User, username: str, ch) -> bool:
        """Subscribe the user from the channel's newest post; returns True when the channel waits in the queue."""
        newest = max((p.last_id for p in ch.posts), default=0)
        last_date = max((p.date for p in ch.posts), default=0)
        if self.store.channel(username) is None:
            full = self.store.active_count() >= self.cfg.max_channels
            now = time.time()
            self.store.add_channel(username, newest, last_date, self.poller.interval(last_date, now), queued=full)
            if not full:
                self.poller.polled[username] = now
        self.store.subscribe(user.id, username, since_id=newest)
        return self.store.channel(username).queued_at is not None

    async def _check(self, user: User, username: str):
        """Read a channel for adding. Returns (channel, None) or (None, the line saying why not)."""
        lang = user.lang
        if not self._rate_ok(user.id):
            return None, RATE
        self._adds[user.id].append(time.time())
        try:
            return await self._read_channel(username), None
        except NotReadable as exc:
            return None, t(exc.reason, lang, c=f"@{username}")
        except httpx.HTTPError as exc:
            self.status.error(f"add: {type(exc).__name__}: {exc}")
            log.warning("add: web view: %s: %s", type(exc).__name__, exc)
            return None, t("try_later", lang, c=f"@{username}")

    async def add(self, chat: int, user: User, names: list[str], bad: list[str],
                  titles: dict | None = None, notes: list[str] | None = None) -> None:
        """One channel is added at once with its latest post as a card; two or more open a checklist."""
        lines = list(notes or [])
        have = {s.channel for s in self.store.subs_of(user.id)}
        lines += [t("already", user.lang, c=f"@{u}") for u in names if u in have]
        fresh = [u for u in names if u not in have]
        lines += [t("bad_ref", user.lang, c=b) for b in bad]
        if len(fresh) >= 2:
            await self.add_many(chat, user, fresh, lines)
            return
        head = []
        for username in fresh:
            if len(have) >= self.cfg.max_subs_per_user:
                lines.insert(0, t("limit_subs", user.lang, n=self.cfg.max_subs_per_user))
                break
            ch, why = await self._check(user, username)
            if ch is None:
                lines.insert(0, t("limit_rate", user.lang, n=self.cfg.max_adds_per_hour) if why is RATE else why)
                break
            title = ch.title or (titles or {}).get(username) or f"@{username}"
            if self._subscribe(user, username, ch):
                lines.insert(0, t("queued", user.lang, c=f"@{username}", n=self.cfg.max_channels))
                break
            posts = [p for p in ch.posts if not p.service]
            if posts:
                await self.api.call("sendMessage", chat_id=chat, **card(f"https://t.me/{ch.username}/{posts[-1].link_id}"))
                head = [t("added_one", user.lang, t=title)]
            else:
                head = [t("added_one", user.lang, t=title), t("no_posts_yet", user.lang, t=title)]
            log.info("a user added a channel")
        text = "\n".join(head + lines)
        if text:
            await self.say(chat, text)

    # bulk adding: a checklist ----------------------------------------------------------------
    async def _typing(self, chat: int) -> None:
        """Telegram's "typing…" while a long list is read; it lasts 5 s, so it is renewed every 4 s."""
        while True:
            try:
                await self.api.call("sendChatAction", chat_id=chat, action="typing")
            except Exception:
                return
            await asyncio.sleep(4)

    async def add_many(self, chat: int, user: User, names: list[str], lines: list[str]) -> None:
        """Read every channel of a list (up to LIST_MAX), then show one checklist message: a button per readable
        channel, the first ones ticked as far as the user's room allows; a tap toggles; Done adds the ticked ones."""
        room = self._room(user)
        found: dict[str, str] = {}
        pages: dict = {}
        if len(names) > LIST_MAX:
            lines.insert(0, t("checked_first", user.lang, n=LIST_MAX, k=len(names) - LIST_MAX))
            names = names[:LIST_MAX]
        typing = asyncio.create_task(self._typing(chat))
        try:
            for i, username in enumerate(names):
                ch, why = await self._check(user, username)
                if why is RATE:
                    lines.insert(0, t("limit_rate", user.lang, n=self.cfg.max_adds_per_hour) + " " +
                                 t("not_checked", user.lang, n=len(names) - i))
                    break
                if ch is None:
                    lines.append(why)
                    continue
                found[username] = ch.title or f"@{username}"
                pages[username] = ch
        finally:
            typing.cancel()
        if not found:
            await self.say(chat, "\n".join(lines) or t("channels_empty", user.lang))
            return
        basket = {"items": found, "ticked": set(list(found)[:max(room, 0)]), "notes": lines, "pages": pages}
        msg = await self.say(chat, self._basket_text(user, basket), reply_markup=self._basket_markup(user, basket))
        self._baskets[(user.id, msg["message_id"])] = basket

    def _room(self, user: User) -> int:
        return self.cfg.max_subs_per_user - len(self.store.subs_of(user.id))

    def _basket_text(self, user: User, basket: dict) -> str:
        head = t("found", user.lang, n=len(basket["items"]), k=len(basket["ticked"]), r=max(self._room(user), 0))
        return "\n\n".join([head] + (["\n".join(basket["notes"])] if basket["notes"] else []))

    def _basket_markup(self, user: User, basket: dict) -> dict:
        rows = [
            [{"text": ("✓ " if u in basket["ticked"] else "") + title, "callback_data": f"k:{u}"}]
            for u, title in basket["items"].items()
        ]
        rows.append([
            {"text": t("btn_cancel", user.lang), "callback_data": "X"},
            {"text": t("btn_done", user.lang), "callback_data": "K", "style": "primary"},
        ])
        return {"inline_keyboard": rows}

    async def _basket_done(self, user: User, basket: dict) -> str:
        """Add the ticked channels; returns the line the checklist message becomes."""
        added, queued = [], []
        for username in basket["items"]:
            if username not in basket["ticked"]:
                continue
            if len(self.store.subs_of(user.id)) >= self.cfg.max_subs_per_user:
                break
            if any(s.channel == username for s in self.store.subs_of(user.id)):
                continue
            # Read when the list was checked: posts published since then still arrive as new ones.
            ch = basket["pages"][username]
            (queued if self._subscribe(user, username, ch) else added).append(basket["items"][username])
        out = []
        if len(added) == 1:
            out.append(t("added_one", user.lang, t=added[0]))
        elif added:
            out.append(t("added_many", user.lang, t=quoted(added, user.lang)))
        out += [t("queued", user.lang, c=title, n=self.cfg.max_channels) for title in queued]
        if added or queued:
            log.info("a user added %d channel(s) from a list", len(added) + len(queued))
        return "\n".join(out)

    async def _flush_forwards(self, chat: int, user_id: int) -> None:
        """Forwarded posts arrive one update each; those sent together (within 1.5 s) become one list."""
        await asyncio.sleep(1.5)
        async with self._locks[user_id]:
            names, notes = self._forwards.pop(user_id, ([], []))
            self._flush_tasks.pop(user_id, None)
            user = self.store.user(user_id)
            if user and (names or notes):
                await self.add(chat, user, names, [], notes=notes)

    # channel list ---------------------------------------------------------------------------
    def channels_view(self, user: User) -> tuple[str, dict | None]:
        subs = self.store.subs_of(user.id)
        if not subs:
            return t("channels_empty", user.lang), None
        rows = [
            [
                {"text": f"@{s.channel}", "url": f"https://t.me/{s.channel}"},
                {
                    "text": t("btn_resume" if s.paused else "btn_pause", user.lang),
                    "callback_data": f"p:{s.channel}",
                    **({"style": "success"} if s.paused else {}),
                },
                {"text": t("btn_remove", user.lang), "callback_data": f"r:{s.channel}", "style": "danger"},
            ]
            for s in subs
        ]
        head = t("channels_head", user.lang, n=len(subs), max=self.cfg.max_subs_per_user)
        return head, {"inline_keyboard": rows}

    async def show_channels(self, chat: int, user: User) -> None:
        # An empty list is one short line: the welcome is said once, on /start, and never repeated.
        text, markup = self.channels_view(user)
        await self.say(chat, text, reply_markup=markup)

    # settings -------------------------------------------------------------------------------
    def settings_view(self, user: User) -> tuple[str, dict]:
        notif = t("off" if user.silent else "on", user.lang)
        return t("settings", user.lang), {"inline_keyboard": [
            [{"text": t("btn_notifications", user.lang, v=notif), "callback_data": "n"}],
            [{"text": t("btn_language", user.lang, v=LANG_NAMES[user.lang]), "callback_data": "l"}],
        ]}

    def language_view(self, user: User) -> dict:
        rows = [[{"text": ("✓ " if code == user.lang else "") + LANG_NAMES[code], "callback_data": f"L:{code}"}] for code in LANGS]
        return {"inline_keyboard": rows + [[{"text": t("btn_back", user.lang), "callback_data": "b"}]]}

    # buttons --------------------------------------------------------------------------------
    async def on_button(self, q: dict) -> None:
        data = q.get("data") or ""
        msg = q.get("message")
        user = self.store.touch_user(q["from"]["id"], lang_of(q["from"].get("language_code")))
        toast = None
        if msg is None:
            await self.api.call("answerCallbackQuery", callback_query_id=q["id"])
            return
        chat, mid = msg["chat"]["id"], msg["message_id"]

        async def edit(text: str, markup: dict | None) -> None:
            try:
                await self.api.call(
                    "editMessageText", chat_id=chat, message_id=mid, text=text,
                    link_preview_options=NO_PREVIEW, reply_markup=markup,
                )
            except ApiError as exc:
                if "not modified" not in exc.description:
                    raise

        if data.startswith("k:") or data in ("K", "X"):
            basket = self._baskets.get((user.id, mid))
            if basket is None:  # the bot restarted since the list was sent
                await self.api.call("deleteMessage", chat_id=chat, message_id=mid)
                toast = t("list_gone", user.lang)
            elif data == "X":
                self._baskets.pop((user.id, mid), None)
                await self.api.call("deleteMessage", chat_id=chat, message_id=mid)
            elif data == "K" and len(basket["ticked"]) > self._room(user):
                room = max(self._room(user), 0)
                toast = t("too_many", user.lang, k=len(basket["ticked"]), r=room, x=len(basket["ticked"]) - room)
            elif data == "K":
                self._baskets.pop((user.id, mid), None)
                text = await self._basket_done(user, basket)
                if text:
                    await edit(text, None)
                else:
                    await self.api.call("deleteMessage", chat_id=chat, message_id=mid)
            else:
                username = data[2:]
                basket["ticked"] ^= {username}
                await edit(self._basket_text(user, basket), self._basket_markup(user, basket))
        elif data.startswith(("p:", "r:")):
            username = data[2:]
            sub = next((s for s in self.store.subs_of(user.id) if s.channel == username), None)
            if sub and data[0] == "p":
                self.store.set_paused(user.id, username, not sub.paused)
                toast = t("toast_resumed" if sub.paused else "toast_paused", user.lang)
            elif sub:
                self.store.unsubscribe(user.id, username)
                toast = t("toast_removed", user.lang)
            text, markup = self.channels_view(user)
            await edit(text, markup)
        elif data == "n":
            self.store.set_silent(user.id, not user.silent)
            await edit(*self.settings_view(self.store.user(user.id)))
        elif data == "l":
            await edit(t("settings", user.lang), self.language_view(user))
        elif data.startswith("L:") and data[2:] in LANGS:
            self.store.set_lang(user.id, data[2:])
            await edit(*self.settings_view(self.store.user(user.id)))
        elif data == "b":
            await edit(*self.settings_view(user))
        elif data == "S":
            self.store.wipe_user(user.id)
            log.info("a user stopped the bot: forgotten")
            await self.api.call("deleteMessage", chat_id=chat, message_id=mid)
            await self.say(chat, t("stopped", user.lang), reply_markup={"remove_keyboard": True})
        elif data == "C":
            await self.api.call("deleteMessage", chat_id=chat, message_id=mid)
        await self.api.call("answerCallbackQuery", callback_query_id=q["id"], text=toast)
