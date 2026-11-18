"""Configuration: a plain JSON file for settings, a systemd credential for the bot token."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    bot_token: str
    state_dir: Path
    # Polling: a channel that posted within `active_window` is read every `fast_interval`
    # seconds, any other every `slow_interval`. One read per channel serves all its readers.
    fast_interval: int = 90
    slow_interval: int = 300
    active_window: int = 7200
    # Limits. `max_channels` caps distinct channels across all users so polling fits the free
    # 1 GB of egress a month (arithmetic in the README); past it new channels wait in a queue.
    max_channels: int = 100
    max_subs_per_user: int = 30
    max_adds_per_hour: int = 60  # channel checks an hour: two full lists of 30
    # On a host with IPv6 but no IPv4 route to the internet (the free VM), connect over IPv6 only,
    # so no connection waits on an IPv4 attempt that can never succeed.
    ipv6_only: bool = False
    status_bucket: str | None = None  # Cloud Storage bucket for status.json, optional
    status_upload_every: float = 900.0  # 15 min: ~3 000 writes a month, inside the free tier


def _credential(name: str) -> str:
    """A secret from systemd's credentials directory, or from $TGFEED_<NAME>_FILE in development."""
    directory = os.environ.get("CREDENTIALS_DIRECTORY")
    if directory and (Path(directory) / name).exists():
        return (Path(directory) / name).read_text().strip()
    path = os.environ.get(f"TGFEED_{name.upper()}_FILE")
    if path and Path(path).exists():
        return Path(path).read_text().strip()
    return ""


def settings_path() -> Path:
    return Path(os.environ.get("TGFEED_CONFIG", "/etc/feedbot/config.json"))


def state_dir(settings: dict | None = None) -> Path:
    return Path(os.environ.get("STATE_DIRECTORY", (settings or {}).get("state_dir", "/var/lib/feedbot")))


def load() -> Config:
    s = json.loads(settings_path().read_text())
    token = _credential("token")
    if not token:
        raise SystemExit("missing secret: token")
    known = {k: s[k] for k in Config.__dataclass_fields__ if k in s and k not in ("bot_token", "state_dir")}
    return Config(bot_token=token, state_dir=state_dir(s), **known)
