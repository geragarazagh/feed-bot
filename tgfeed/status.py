"""Health: what /status answers, status.json on disk, an optional public copy in Cloud Storage,
and the systemd watchdog."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
import shutil
import socket
import time
import urllib.request
from datetime import datetime, timezone

from . import __version__
from .config import Config
from .store import Store

log = logging.getLogger("tgfeed.status")

METADATA_TOKEN = "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token"


def sd_notify(message: str) -> None:
    """Tell systemd something (READY=1, WATCHDOG=1); a no-op outside systemd."""
    address = os.environ.get("NOTIFY_SOCKET")
    if not address:
        return
    if address.startswith("@"):
        address = "\0" + address[1:]
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
        sock.connect(address)
        sock.sendall(message.encode())


def iso(ts: float | None) -> str | None:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="seconds") if ts else None


class Status:
    def __init__(self, cfg: Config, store: Store):
        self.cfg = cfg
        self.store = store
        self.started_at = time.time()
        self.bot_ok_at: float | None = None  # last answer from getUpdates
        self.last_poll_at: float | None = None  # last polling round
        self.last_delivery_at: float | None = None
        self.last_error: str | None = None
        self.last_error_at: float | None = None
        self.last_upload_at: float | None = None

    def error(self, text: str) -> None:
        self.last_error, self.last_error_at = text[:300], time.time()

    def healthy(self) -> bool:
        """Alive enough for the systemd watchdog: updates arrive and polling rounds go on."""
        now = time.time()
        return (
            self.bot_ok_at is not None
            and now - self.bot_ok_at < 180
            and self.last_poll_at is not None
            and now - self.last_poll_at < 600
        )

    def snapshot(self) -> dict:
        """Public-safe summary: numbers only, no user ids, no channel names."""
        disk = shutil.disk_usage(self.cfg.state_dir)
        sent, polls = self.store.counted(24)
        return {
            "service": "tg-feed",
            "version": __version__,
            "updated_at": iso(time.time()),
            "started_at": iso(self.started_at),
            "healthy": self.healthy(),
            "users": self.store.user_count(),
            "channels": {
                "active": self.store.active_count(),
                "queued": len(self.store.channels(queued=True)),
                "cap": self.cfg.max_channels,
            },
            "deliveries_24h": sent,
            "reads_24h": polls,
            "last_poll_at": iso(self.last_poll_at),
            "last_delivery_at": iso(self.last_delivery_at),
            "last_error": self.last_error,
            "last_error_at": iso(self.last_error_at),
            "host": {
                "uptime_s": int(float(open("/proc/uptime").read().split()[0])) if os.path.exists("/proc/uptime") else None,
                "mem_available_mb": _mem_available_mb(),
                "disk_free_gb": round(disk.free / 2**30, 1),
                # Internet egress is billable past the free 1 GB a month; on this VM it is all IPv6.
                "ipv6_out_mb_since_boot": _ipv6_out_mb(),
            },
        }

    def write_local(self) -> bytes:
        data = json.dumps(self.snapshot(), ensure_ascii=False, indent=1).encode()
        path = self.cfg.state_dir / "status.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)
        return data

    async def run(self) -> None:
        """Every 30 s: status.json on disk and a watchdog ping; every 15 min: the public copy."""
        while True:
            try:
                data = self.write_local()
                if self.healthy():
                    sd_notify("WATCHDOG=1")
                if self.last_upload_at is None:
                    # The first public copy waits for a healthy state (or 2 min), so a restart never
                    # publishes a false "unhealthy" for the next 15 minutes.
                    due = self.healthy() or time.time() - self.started_at > 120
                else:
                    due = time.time() - self.last_upload_at >= self.cfg.status_upload_every
                if self.cfg.status_bucket and due:
                    self.last_upload_at = time.time()  # also on failure: never hammer the bucket
                    await asyncio.to_thread(_upload, self.cfg.status_bucket, data)
            except Exception as exc:  # status must never take the service down
                log.warning("status: %s", exc)
            await asyncio.sleep(30)


def _mem_available_mb() -> int | None:
    try:
        for line in open("/proc/meminfo"):
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) // 1024
    except OSError:
        pass
    return None


def _ipv6_out_mb() -> float | None:
    try:
        for line in open("/proc/net/snmp6"):
            if line.startswith("Ip6OutOctets"):
                return round(int(line.split()[1]) / 2**20, 2)
    except OSError:
        pass
    return None


def _upload(bucket: str, data: bytes) -> None:
    """Overwrite gs://bucket/status.json with the VM's service account (one Class A operation)."""
    token_req = urllib.request.Request(METADATA_TOKEN, headers={"Metadata-Flavor": "Google"})
    with urllib.request.urlopen(token_req, timeout=10) as resp:
        token = json.load(resp)["access_token"]
    boundary = "tgfeed" + secrets.token_hex(8)
    meta = json.dumps({"name": "status.json", "contentType": "application/json", "cacheControl": "no-store"})
    body = (
        f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{meta}\r\n"
        f"--{boundary}\r\nContent-Type: application/json\r\n\r\n"
    ).encode() + data + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        f"https://storage.googleapis.com/upload/storage/v1/b/{bucket}/o?uploadType=multipart",
        data=body,
        method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": f"multipart/related; boundary={boundary}"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        resp.read()
