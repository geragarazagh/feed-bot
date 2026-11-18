import tempfile
import unittest
from pathlib import Path

from tgfeed.store import Store


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.dir.name) / "t.db")

    def tearDown(self):
        self.dir.cleanup()

    def test_user_language_follows_app_until_chosen(self):
        s = self.store
        self.assertEqual(s.touch_user(1, "ru").lang, "ru")
        self.assertEqual(s.touch_user(1, "uk").lang, "uk")
        s.set_lang(1, "en")
        self.assertEqual(s.touch_user(1, "ru").lang, "en")

    def test_subscriptions_and_orphans(self):
        s = self.store
        s.touch_user(1, "en")
        s.touch_user(2, "en")
        s.add_channel("durov", 500, 1000, 300, queued=False)
        self.assertTrue(s.subscribe(1, "durov", 500))
        self.assertFalse(s.subscribe(1, "durov", 500))
        s.subscribe(2, "durov", 500)
        s.set_paused(2, "durov", True)
        self.assertEqual([x.user_id for x in s.readers("durov")], [1])
        s.unsubscribe(1, "durov")
        self.assertIsNotNone(s.channel("durov"))  # user 2 still has it
        s.wipe_user(2)
        self.assertIsNone(s.channel("durov"))  # nobody reads it: gone
        self.assertEqual(s.user_count(), 1)

    def test_advance_never_goes_back(self):
        s = self.store
        s.add_channel("durov", 500, 1000, 300, queued=False)
        s.advance("durov", 510, 2000, 90)
        s.advance("durov", 505, None, 300)
        c = s.channel("durov")
        self.assertEqual((c.last_id, c.last_post_at, c.interval), (510, 2000, 300))

    def test_queue(self):
        s = self.store
        s.add_channel("a", 1, 1, 300, queued=False)
        s.add_channel("b", 1, 1, 300, queued=True)
        self.assertEqual(s.active_count(), 1)
        self.assertEqual([c.username for c in s.channels(queued=True)], ["b"])
        s.unqueue("b", 7, 9)
        self.assertEqual(s.active_count(), 2)

    def test_counts(self):
        s = self.store
        s.count(sent=2)
        s.count(sent=1, polls=5)
        self.assertEqual(s.counted(24), (3, 5))
