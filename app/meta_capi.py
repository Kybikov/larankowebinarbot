from __future__ import annotations

import hashlib
import logging
import time
from typing import Any

import aiohttp

from app.config import Settings


logger = logging.getLogger(__name__)


class MetaConversionsClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def send_event(
        self,
        *,
        event_name: str,
        attribution: dict[str, Any] | None,
        telegram_id: int | str | None = None,
        event_id: str | None = None,
    ) -> bool:
        pixel_id = str((attribution or {}).get("pixel_id") or self.settings.meta_pixel_id).strip()
        access_token = self.settings.meta_access_token
        if not pixel_id or not access_token:
            logger.info("Meta CAPI skipped for %s: META_PIXEL_ID or META_ACCESS_TOKEN is empty", event_name)
            return False

        user_data = self._user_data(attribution or {}, telegram_id)
        if not user_data:
            logger.info("Meta CAPI skipped for %s: no user_data available", event_name)
            return False

        payload = {
            "data": [
                {
                    "event_name": event_name,
                    "event_time": int(time.time()),
                    "event_id": event_id,
                    "action_source": self.settings.meta_action_source or "website",
                    "event_source_url": (attribution or {}).get("source_url") or self.settings.attribution_public_base_url,
                    "user_data": user_data,
                }
            ]
        }
        if self.settings.meta_test_event_code:
            payload["test_event_code"] = self.settings.meta_test_event_code
        payload["data"][0] = {key: value for key, value in payload["data"][0].items() if value}

        url = f"https://graph.facebook.com/v19.0/{pixel_id}/events"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, params={"access_token": access_token}, json=payload, timeout=10) as response:
                    body = await response.text()
                    if response.status >= 400:
                        logger.warning("Meta CAPI %s failed with %s: %s", event_name, response.status, body)
                        return False
                    logger.info("Meta CAPI %s sent: %s", event_name, body)
                    return True
        except Exception:
            logger.exception("Meta CAPI %s failed", event_name)
            return False

    def _user_data(self, attribution: dict[str, Any], telegram_id: int | str | None) -> dict[str, str]:
        user_data: dict[str, str] = {}
        if attribution.get("ip_address"):
            user_data["client_ip_address"] = str(attribution["ip_address"])
        if attribution.get("user_agent"):
            user_data["client_user_agent"] = str(attribution["user_agent"])
        if attribution.get("fbp"):
            user_data["fbp"] = str(attribution["fbp"])
        fbc = attribution.get("fbc") or self._fbc_from_fbclid(attribution.get("fbclid"))
        if fbc:
            user_data["fbc"] = fbc
        if telegram_id:
            user_data["external_id"] = hashlib.sha256(str(telegram_id).encode()).hexdigest()
        return user_data

    def _fbc_from_fbclid(self, fbclid: Any) -> str:
        fbclid = str(fbclid or "").strip()
        if not fbclid:
            return ""
        return f"fb.1.{int(time.time())}.{fbclid}"
