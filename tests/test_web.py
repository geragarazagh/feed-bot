"""The web-view parser against markup shaped like t.me/s/<channel> (trimmed from real pages)."""

import json
import unittest

from tgfeed.web import classify, parse_posts

WRAP = '<div class="tgme_widget_message_wrap js-widget_message_wrap"><div class="tgme_widget_message {cls}js-widget_message" data-post="chan/{id}" data-view="x">'
TIME = '<a class="tgme_widget_message_date" href="https://t.me/chan/{id}"><time datetime="{dt}" class="time">12:00</time></a></div></div>'
SINGLE = '<a class="tgme_widget_message_photo_wrap grouped_media_wrap" href="https://t.me/chan/{id}?single"></a>'


def post(i, dt, album=(), service=False):
    body = "".join(SINGLE.format(id=a) for a in album)
    return WRAP.format(cls="service_message " if service else "", id=i) + body + TIME.format(id=i, dt=dt)


class ParsePosts(unittest.TestCase):
    def test_plain_album_service(self):
        html = (post(10, "2026-11-17T10:00:00+00:00", service=True)
                + post(11, "2026-11-17T11:00:00+00:00")
                + post(12, "2026-11-17T12:00:00+00:00", album=(12, 13, 14)))
        posts = parse_posts(html)
        self.assertEqual([(p.link_id, p.last_id, p.service) for p in posts],
                         [(10, 10, True), (11, 11, False), (12, 14, False)])
        self.assertEqual(posts[1].date, 1794913200)

    def test_load_newer_answer_is_a_json_string(self):
        answer = json.dumps(post(20, "2026-11-17T11:00:00+00:00"))
        self.assertEqual(parse_posts(json.loads(answer))[0].link_id, 20)


class Classify(unittest.TestCase):
    def test_kinds(self):
        self.assertEqual(classify('<div class="tgme_page_extra">8 990 subscribers</div>'), "preview_off")
        self.assertEqual(classify('<div class="tgme_page_extra">17 368 members, 1 572 online</div>'), "group")
        self.assertEqual(classify('<div class="tgme_page_extra"></div>'), "not_channel")
