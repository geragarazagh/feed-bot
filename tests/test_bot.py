"""The bot and the poller against a fake Bot API and a fake web view (no network)."""

import asyncio
import tempfile
import time
import unittest
from pathlib import Path

from tgfeed.api import ApiError
from tgfeed.bot import Bot
from tgfeed.config import Config
from tgfeed.poller import Poller, Sender
from tgfeed.status import Status
from tgfeed.store import Store
from tgfeed.web import Channel, NotReadable, Post

ME = 111111111
NOW = int(time.time())


class FakeApi:
    def __init__(self):
        self.calls = []
        self.fail = {}  # chat_id -> ApiError

    async def call(self, method, files=None, **params):
        if params.get("chat_id") in self.fail and method == "sendMessage":
            raise self.fail[params["chat_id"]]
        self.calls.append((method, params))
        return {"message_id": len(self.calls)}

    def sent(self):
        return [p for m, p in self.calls if m == "sendMessage"]


class FakeWeb:
    def __init__(self):
        self.pages = {
            "durov": Channel("durov", "Durov's Channel", [Post(500, 500, NOW - 60, False), Post(501, 503, NOW - 30, False)]),
            "quiet": Channel("quiet", "Quiet", []),
        }
        self.newer_posts = {}

    async def channel(self, username):
        if username == "closed":
            raise NotReadable("preview_off")
        if username == "agroup":
            raise NotReadable("group")
        if username not in self.pages:  # any other name: a channel with one post
            return Channel(username, f"Title {username}", [Post(7, 7, NOW - 9000, False)])
        return self.pages[username]

    async def newer(self, username, after):
        return [p for p in self.newer_posts.get(username, []) if p.last_id > after]


class BotTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.cfg = Config(bot_token="x", state_dir=Path(self.dir.name), max_channels=2)
        self.store = Store(self.cfg.state_dir / "t.db")
        self.status = Status(self.cfg, self.store)
        self.api = FakeApi()
        self.web = FakeWeb()
        self.sender = Sender(self.api, self.store, self.status)
        self.poller = Poller(self.cfg, self.store, self.web, self.sender, self.status)
        self.bot = Bot(self.cfg, self.store, self.api, self.web, self.sender, self.poller, self.status)

    async def asyncTearDown(self):
        self.dir.cleanup()

    def msg(self, text=None, lang="ru", user=ME, **extra):
        m = {"chat": {"id": user, "type": "private"}, "from": {"id": user, "language_code": lang}, "message_id": 1}
        if text is not None:
            m["text"] = text
        m.update(extra)
        return m

    async def test_start_shows_picker_in_users_language(self):
        await self.bot.on_message(self.msg("/start", lang="uk"))
        sent = self.api.sent()[-1]
        button = sent["reply_markup"]["keyboard"][0][0]
        self.assertEqual(button["text"], "Виберіть канал")
        self.assertTrue(button["request_chat"]["chat_is_channel"])

    async def test_add_sends_latest_post_card_then_one_line(self):
        await self.bot.on_message(self.msg("@durov"))
        cardmsg, line = self.api.sent()[-2:]
        self.assertEqual(cardmsg["text"], "https://t.me/durov/501")  # an album: its first part
        self.assertEqual(cardmsg["link_preview_options"],
                         {"url": "https://t.me/durov/501", "prefer_large_media": True, "show_above_text": True})
        self.assertEqual(line["text"], "Новые публикации канала «Durov's Channel» будут приходить сюда.")
        self.assertEqual(self.store.channel("durov").last_id, 503)
        await self.bot.on_message(self.msg("t.me/durov"))
        self.assertEqual(self.api.sent()[-1]["text"], "@durov уже в Вашем списке.")

    async def test_refusals(self):
        await self.bot.on_message(self.msg("@closed @agroup t.me/+abc", lang="en"))
        text = self.api.sent()[-1]["text"]
        self.assertIn("doesn't show the posts of @closed on the web", text)
        self.assertIn("@agroup is a group", text)
        self.assertIn("t.me/+abc is not a link", text)
        self.assertIsNone(self.store.channel("closed"))

    async def test_forward_and_picker(self):
        await self.bot.on_message(self.msg(forward_origin={"type": "channel", "chat": {"username": "Durov"}, "message_id": 5}))
        await asyncio.sleep(1.7)  # forwards are gathered for 1.5 s; one channel is added at once
        self.assertEqual(self.store.subs_of(ME)[0].channel, "durov")
        await self.bot.on_message(self.msg(chat_shared={"request_id": 1, "chat_id": -100, "username": "quiet", "title": "Quiet"}))
        self.assertIn("пока нет публикаций", self.api.sent()[-1]["text"])
        await self.bot.on_message(self.msg(forward_origin={"type": "user", "sender_user": {"id": 1}}))
        await asyncio.sleep(1.7)
        self.assertIn("не из канала", self.api.sent()[-1]["text"])

    async def test_forwarded_batch_becomes_one_checklist(self):
        for name in ("alpha_one", "beta_two", "alpha_one"):
            await self.bot.on_message(self.msg(forward_origin={"type": "channel", "chat": {"username": name}}, lang="en"))
        await self.bot.on_message(self.msg(forward_origin={"type": "user", "sender_user": {"id": 1}}, lang="en"))
        await asyncio.sleep(1.7)
        sent = self.api.sent()
        self.assertEqual(len(sent), 1)  # one message for the whole batch
        self.assertTrue(sent[0]["text"].startswith("Channels found: 2. Selected: 2."))
        self.assertIn("not from a channel", sent[0]["text"])

    async def test_pasted_list_of_100(self):
        names = " ".join(f"@chan{i:03d}" for i in range(100))
        await self.bot.on_message(self.msg(names, lang="en"))
        sent = self.api.sent()
        self.assertEqual(len(sent), 1)  # one reply: the checklist
        rows = sent[0]["reply_markup"]["inline_keyboard"]
        self.assertEqual(len(rows), 31)  # 30 channels and the Cancel/Done row
        self.assertEqual(rows[0][0]["text"], "✓ Title chan000")
        self.assertEqual([b["text"] for b in rows[-1]], ["Cancel", "Done"])
        self.assertIn("Channels found: 30. Selected: 30.", sent[0]["text"])
        self.assertIn("A list holds up to 30 channels, so 70 more were not checked.", sent[0]["text"])
        mid = next(iter(self.bot._baskets))[1]
        q = {"id": "q", "from": {"id": ME, "language_code": "en"}, "message": {"chat": {"id": ME}, "message_id": mid}}
        await self.bot.on_button({**q, "data": "k:chan001"})  # untick one
        edits = [p for m, p in self.api.calls if m == "editMessageText"]
        self.assertIn("Selected: 29.", edits[-1]["text"])
        self.assertEqual(edits[-1]["reply_markup"]["inline_keyboard"][1][0]["text"], "Title chan001")
        await self.bot.on_button({**q, "data": "K"})
        self.assertEqual(len(self.store.subs_of(ME)), 29)
        edits = [p for m, p in self.api.calls if m == "editMessageText"]
        self.assertTrue(edits[-1]["text"].startswith("New posts from these channels will come here: “Title chan000”, “Title chan002”"))
        self.assertIsNone(edits[-1]["reply_markup"])
        self.assertEqual(len(self.api.sent()), 1)  # no cards flood for a list

    async def test_checklist_cancel(self):
        await self.bot.on_message(self.msg("@aaaa1 @bbbb2", lang="en"))
        mid = next(iter(self.bot._baskets))[1]
        q = {"id": "q", "data": "X", "from": {"id": ME, "language_code": "en"}, "message": {"chat": {"id": ME}, "message_id": mid}}
        await self.bot.on_button(q)
        self.assertEqual(self.store.subs_of(ME), [])
        self.assertEqual(self.api.calls[-2][0], "deleteMessage")

    async def test_cap_queues_new_channels(self):
        self.store.add_channel("a1", 1, 1, 300, queued=False)
        self.store.add_channel("a2", 1, 1, 300, queued=False)
        await self.bot.on_message(self.msg("@durov", lang="en"))
        self.assertIn("in the queue", self.api.sent()[-1]["text"])
        self.assertIsNotNone(self.store.channel("durov").queued_at)

    async def test_limits(self):
        cfg = Config(bot_token="x", state_dir=self.cfg.state_dir, max_adds_per_hour=1)
        self.bot.cfg = cfg
        await self.bot.on_message(self.msg("@durov @quiet", lang="en"))
        text = self.api.sent()[-1]["text"]
        self.assertIn("up to 1 channels an hour", text)
        self.assertIn("1 more were not checked", text)

    async def test_channels_buttons_pause_remove_then_start(self):
        await self.bot.on_message(self.msg("@durov", lang="en"))
        await self.bot.on_message(self.msg("/channels", lang="en"))
        rows = self.api.sent()[-1]["reply_markup"]["inline_keyboard"]
        self.assertEqual([b["text"] for b in rows[0]], ["@durov", "Pause", "Remove"])
        self.assertEqual(rows[0][2]["style"], "danger")
        q = {"id": "q", "from": {"id": ME, "language_code": "en"}, "message": {"chat": {"id": ME}, "message_id": 9}}
        await self.bot.on_button({**q, "data": "p:durov"})
        self.assertTrue(self.store.subs_of(ME)[0].paused)
        await self.bot.on_button({**q, "data": "r:durov"})
        self.assertEqual(self.store.subs_of(ME), [])
        self.assertEqual([p for m, p in self.api.calls if m == "editMessageText"][-1]["text"], "Your list is empty.")  # one line, no repeated welcome

    async def test_settings_language_and_silent(self):
        await self.bot.on_message(self.msg("/settings", lang="ru"))
        q = {"id": "q", "from": {"id": ME, "language_code": "ru"}, "message": {"chat": {"id": ME}, "message_id": 9}}
        await self.bot.on_button({**q, "data": "L:en"})
        self.assertEqual(self.store.user(ME).lang, "en")
        await self.bot.on_button({**q, "data": "n"})
        self.assertTrue(self.store.user(ME).silent)
        edits = [p for m, p in self.api.calls if m == "editMessageText"]
        self.assertEqual(edits[-1]["reply_markup"]["inline_keyboard"][0][0]["text"], "Notifications: Off")

    async def test_no_owner_commands(self):
        # Everyone gets the same bot: /status is an unknown command like any other.
        await self.bot.on_message(self.msg("/status", lang="en"))
        self.assertTrue(self.api.sent()[-1]["text"].startswith("New posts of the channels you choose"))

    async def test_stop_wipes(self):
        await self.bot.on_message(self.msg("@durov"))
        q = {"id": "q", "data": "S", "from": {"id": ME, "language_code": "ru"}, "message": {"chat": {"id": ME}, "message_id": 9}}
        await self.bot.on_button(q)
        self.assertIsNone(self.store.user(ME))
        self.assertIsNone(self.store.channel("durov"))
        self.assertEqual(self.api.sent()[-1]["reply_markup"], {"remove_keyboard": True})

    async def test_block_wipes(self):
        await self.bot.on_message(self.msg("@durov"))
        await self.bot.on_member({"chat": {"id": ME, "type": "private"}, "new_chat_member": {"status": "kicked"}})
        self.assertIsNone(self.store.user(ME))

    async def test_poll_round_order_since_and_403(self):
        other = 42
        await self.bot.on_message(self.msg("@durov"))
        await self.bot.on_message(self.msg("@quiet", user=other))
        self.store.add_channel("x", 0, 0, 300, queued=False)
        # A new post in each channel; quiet's is older and must go first.
        self.web.newer_posts = {
            "durov": [Post(504, 504, NOW - 5, False)],
            "quiet": [Post(1, 2, NOW - 20, False), Post(3, 3, NOW - 10, True)],
        }
        self.poller.polled.clear()
        await self.poller._round()
        items = sorted(self.sender._heap)
        self.assertEqual([i.params["text"] for i in items], ["https://t.me/quiet/1", "https://t.me/durov/504"])
        self.assertEqual(self.store.channel("quiet").last_id, 3)  # service post passed, not sent
        self.assertEqual(self.store.channel("durov").interval, 90)  # active: read often
        # The quiet channel's reader blocked the bot: the send fails with 403 and the user is forgotten.
        self.api.fail[other] = ApiError("sendMessage", 403, "Forbidden: bot was blocked by the user")
        for item in list(items):
            await self.sender._send(item)
        self.assertIsNone(self.store.user(other))
        self.assertIsNone(self.store.channel("quiet"))
        self.assertEqual(self.store.counted(1)[0], 1)

    async def test_closed_channel_dropped_after_strikes(self):
        await self.bot.on_message(self.msg("@durov"))

        async def closed(username, after):
            raise NotReadable("preview_off")

        self.web.newer = closed
        for _ in range(3):
            self.poller.polled.clear()
            await self.poller._round()
        self.assertIsNone(self.store.channel("durov"))
        self.assertIn("больше не показывает", sorted(self.sender._heap)[-1].params["text"])

    async def test_promote_queued(self):
        self.store.touch_user(ME, "en")
        self.store.add_channel("durov", 1, 1, 300, queued=True)
        self.store.subscribe(ME, "durov", 1)
        await self.poller._promote()
        texts = [i.params["text"] for i in sorted(self.sender._heap)]
        self.assertEqual(texts, ["https://t.me/durov/501", "New posts from “Durov's Channel” will come here."])
        self.assertIsNone(self.store.channel("durov").queued_at)


class Texts(unittest.TestCase):
    def test_profile_limits(self):
        from tgfeed.texts import LANGS, T
        for lang in LANGS:
            self.assertLessEqual(len(T["about"][lang]), 120)
            self.assertLessEqual(len(T["description"][lang]), 512)
            self.assertLessEqual(len(T["name"][lang]), 64)

    def test_same_placeholders(self):
        import string
        from tgfeed.texts import T
        for key, by_lang in T.items():
            fields = {lang: {f for _, f, _, _ in string.Formatter().parse(s) if f} for lang, s in by_lang.items()}
            self.assertEqual(len({frozenset(v) for v in fields.values()}), 1, key)
