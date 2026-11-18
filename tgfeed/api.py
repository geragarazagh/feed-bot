"""A thin Bot API client over HTTPS (api.telegram.org answers on IPv6, so the IPv4-less VM reaches it)."""

from __future__ import annotations

import asyncio
import json
import logging

import httpx

log = logging.getLogger("tgfeed.api")


class ApiError(Exception):
    def __init__(self, method: str, code: int, description: str, retry_after: int | None = None):
        super().__init__(f"{method}: {code} {description}")
        self.code = code
        self.description = description
        self.retry_after = retry_after

    @property
    def user_gone(self) -> bool:
        """The user blocked the bot or deleted the account: the bot must forget them."""
        d = self.description.lower()
        return self.code == 403 and ("blocked" in d or "deactivated" in d)

    @property
    def not_started(self) -> bool:
        """The user never pressed Start: nothing may be sent yet, nothing is wiped."""
        d = self.description.lower()
        return (self.code == 403 and "initiate" in d) or (self.code == 400 and "chat not found" in d)


class Api:
    def __init__(self, token: str, ipv6_only: bool = False):
        self.base = f"https://api.telegram.org/bot{token}/"
        self.http = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, read=70.0),  # getUpdates holds the request up to 50 s
            transport=httpx.AsyncHTTPTransport(
                limits=httpx.Limits(max_connections=4, max_keepalive_connections=4, keepalive_expiry=120),
                local_address="::" if ipv6_only else None,
            ),
        )

    async def close(self) -> None:
        await self.http.aclose()

    async def call(self, method: str, files: dict | None = None, **params):
        """Call a method; None values are left out, dicts and lists go as JSON. Retries a flood
        wait once and a network error twice."""
        data = {k: v for k, v in params.items() if v is not None}
        for attempt in range(3):
            try:
                if files:
                    form = {k: json.dumps(v) if isinstance(v, (dict, list)) else str(v) for k, v in data.items()}
                    r = await self.http.post(self.base + method, data=form, files=files)
                else:
                    r = await self.http.post(self.base + method, json=data)
                body = r.json()
            except (httpx.TransportError, ValueError) as exc:
                if attempt == 2:
                    raise
                log.warning("%s: %s, retrying", method, type(exc).__name__)
                await asyncio.sleep(2 + 3 * attempt)
                continue
            if body.get("ok"):
                return body["result"]
            retry = (body.get("parameters") or {}).get("retry_after")
            err = ApiError(method, body.get("error_code", r.status_code), body.get("description", ""), retry)
            if err.code == 429 and retry and attempt < 2:
                await asyncio.sleep(retry + 1)
                continue
            raise err
        raise RuntimeError("unreachable")
