from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

from aiohttp import web

from app.config import Settings
from app.pocketbase import PocketBaseClient


logger = logging.getLogger(__name__)


def build_attribution_app(settings: Settings, pb: PocketBaseClient) -> web.Application:
    app = web.Application()

    async def telegram_start(request: web.Request) -> web.Response:
        token = _token()
        query = request.rel_url.query
        pixel_id = (query.get("pixel") or settings.meta_pixel_id).strip()
        source_url = query.get("source_url") or query.get("landing_url") or str(request.url)
        user_agent = request.headers.get("User-Agent", "")
        referrer = request.headers.get("Referer", query.get("referrer", ""))
        ip_address = _client_ip(request)
        now = datetime.now(timezone.utc).isoformat()
        await pb.create_record(
            "attribution_tokens",
            {
                "token": token,
                "pixel_id": pixel_id,
                "fbclid": query.get("fbclid", ""),
                "fbc": query.get("fbc", ""),
                "fbp": query.get("fbp", ""),
                "utm": _utm(query),
                "source_url": source_url,
                "referrer": referrer,
                "user_agent": user_agent,
                "ip_address": ip_address,
                "status": "created",
                "created_at": now,
                "started_at": "",
                "registered_at": "",
                "telegram_id": "",
                "user": "",
                "start_event_id": "",
                "registration_event_id": "",
            },
        )
        bot_url = f"https://t.me/{settings.bot_username}?{urlencode({'start': token})}"
        logger.info("Attribution token %s created, redirecting to Telegram", token)
        raise web.HTTPFound(bot_url)

    async def health(_: web.Request) -> web.Response:
        return web.json_response({"ok": True})

    app.router.add_get("/tg/start", telegram_start)
    app.router.add_get("/health", health)
    return app


async def start_attribution_server(settings: Settings, pb: PocketBaseClient) -> web.AppRunner:
    app = build_attribution_app(settings, pb)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, settings.attribution_host, settings.attribution_port)
    await site.start()
    logger.info("Attribution server listening on %s:%s", settings.attribution_host, settings.attribution_port)
    return runner


def _token() -> str:
    return "src_" + secrets.token_urlsafe(18).replace("-", "").replace("_", "")[:24]


def _utm(query: Any) -> dict[str, str]:
    return {
        key: query.get(key, "")
        for key in ("utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term")
        if query.get(key)
    }


def _client_ip(request: web.Request) -> str:
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    real_ip = request.headers.get("X-Real-IP", "")
    if real_ip:
        return real_ip.strip()
    peername = request.transport.get_extra_info("peername") if request.transport else None
    return str(peername[0]) if peername else ""
