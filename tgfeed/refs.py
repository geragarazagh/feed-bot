"""Parsing what users send as a channel: '@name', 'name', 't.me/name', 'https://t.me/s/name/123'."""

from __future__ import annotations

import re

_LINK_PREFIX = re.compile(r"^(?:https?://)?(?:www\.)?(?:t\.me|telegram\.me|telegram\.dog)/", re.I)
# Public usernames: a letter first, then letters, digits and underscores, 4 to 32 characters.
_USERNAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]{3,31}$")
# t.me paths that are not usernames.
_RESERVED = {"joinchat", "addstickers", "addemoji", "addlist", "share", "proxy", "socks", "login", "setlanguage", "c"}
_TOKEN = re.compile(r"(?:https?://)?(?:www\.)?(?:t\.me|telegram\.me|telegram\.dog)/\S+|@[A-Za-z][A-Za-z0-9_]{3,31}", re.I)


def parse_channel_ref(text: str) -> str | None:
    """Turn one reference into a lower-case username, or None for anything that is not a public
    username (invite links, numeric ids, garbage)."""
    ref = _LINK_PREFIX.sub("", text.strip().rstrip(".,;)"))
    if ref.lower().startswith("s/"):
        ref = ref[2:]
    ref = ref.lstrip("@").split("?", 1)[0].split("/", 1)[0]
    if not _USERNAME.match(ref) or ref.lower() in _RESERVED:
        return None
    return ref.lower()


def extract_refs(text: str) -> tuple[list[str], list[str]]:
    """All channel references in a message: (usernames in order without repeats, unparsable tokens).

    A message that is a single bare word ('durov') counts too; inside longer text only @names and
    t.me links count, so ordinary words are never taken for channels.
    """
    text = text.strip()
    tokens = _TOKEN.findall(text)
    if not tokens and len(text.split()) == 1:
        tokens = [text]
    names, bad = [], []
    for t in tokens:
        u = parse_channel_ref(t)
        if u is None:
            bad.append(t)
        elif u not in names:
            names.append(u)
    return names, bad
