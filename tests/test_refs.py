import unittest

from tgfeed.refs import extract_refs, parse_channel_ref


class ParseChannelRef(unittest.TestCase):
    def test_forms(self):
        for text in ("@Durov", "durov", "t.me/durov", "https://t.me/durov", "https://t.me/s/durov",
                     "https://t.me/durov/563", "http://www.telegram.me/durov?single", " @durov ", "@durov,"):
            self.assertEqual(parse_channel_ref(text), "durov", text)

    def test_rejects(self):
        for text in ("https://t.me/+AbCdEf", "t.me/joinchat/xyz", "-1001234567890", "@a", "1abc", "", "@",
                     "https://t.me/c/123/45"):
            self.assertIsNone(parse_channel_ref(text), text)


class ExtractRefs(unittest.TestCase):
    def test_several_in_text(self):
        names, bad = extract_refs("add @durov and https://t.me/telegram/1 also t.me/+invite please")
        self.assertEqual(names, ["durov", "telegram"])
        self.assertEqual(bad, ["t.me/+invite"])

    def test_bare_word_only_alone(self):
        self.assertEqual(extract_refs("durov"), (["durov"], []))
        self.assertEqual(extract_refs("hello there"), ([], []))

    def test_no_repeats(self):
        self.assertEqual(extract_refs("@durov t.me/Durov")[0], ["durov"])
