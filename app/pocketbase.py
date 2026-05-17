from __future__ import annotations

import asyncio
import csv
import io
import json
from datetime import datetime, timezone
from typing import Any

import aiohttp

from app.config import Settings


class PocketBaseError(RuntimeError):
    pass


USER_COLLECTION = "tg_users"


class PocketBaseClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._token: str | None = None
        self._session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> "PocketBaseClient":
        self._session = aiohttp.ClientSession()
        await self.wait_until_ready()
        await self.auth_admin()
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._session:
            await self._session.close()

    @property
    def session(self) -> aiohttp.ClientSession:
        if not self._session:
            raise PocketBaseError("PocketBase client is not started")
        return self._session

    async def wait_until_ready(self, timeout: int = 60) -> None:
        last_error: Exception | None = None
        for _ in range(timeout):
            try:
                async with self.session.get(f"{self.settings.pocketbase_url}/api/health") as response:
                    if response.status < 500:
                        return
            except Exception as exc:  # pragma: no cover - network timing
                last_error = exc
            await asyncio.sleep(1)
        raise PocketBaseError(f"PocketBase is not reachable: {last_error}")

    async def auth_admin(self) -> None:
        payload = {
            "identity": self.settings.pocketbase_admin_email,
            "password": self.settings.pocketbase_admin_password,
        }
        data = await self._request(
            "POST",
            "/api/admins/auth-with-password",
            json=payload,
            auth=False,
        )
        self._token = data["token"]

    async def _request(
        self,
        method: str,
        path: str,
        *,
        auth: bool = True,
        **kwargs: Any,
    ) -> Any:
        headers = kwargs.pop("headers", {})
        if auth and self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        async with self.session.request(
            method,
            f"{self.settings.pocketbase_url}{path}",
            headers=headers,
            **kwargs,
        ) as response:
            if response.status >= 400:
                body = await response.text()
                raise PocketBaseError(f"{method} {path} failed with {response.status}: {body}")
            if response.status == 204:
                return None
            return await response.json()

    async def ensure_schema(self) -> None:
        collections = await self._request("GET", "/api/collections?perPage=200")
        existing = {item["name"]: item for item in collections.get("items", [])}
        for collection in collection_definitions():
            if collection["name"] not in existing:
                await self._request("POST", "/api/collections", json=collection)
                continue
            existing_collection = existing[collection["name"]]
            existing_fields = {field["name"] for field in existing_collection.get("schema", [])}
            missing_fields = [field for field in collection["schema"] if field["name"] not in existing_fields]
            if missing_fields:
                await self._request(
                    "PATCH",
                    f"/api/collections/{existing_collection['id']}",
                    json={"schema": [*existing_collection.get("schema", []), *missing_fields]},
                )

    async def ensure_default_webinar(self) -> None:
        items = await self.list_records(
            "webinars",
            filter_='slug="laranko-remont-bez-haosu-2026-05-20"',
            per_page=1,
        )
        if items:
            return

        from app.content import (
            CONFIRMATION_TEXT,
            WEBINAR_TITLE,
            WELCOME_TEXT,
            default_scheduled_messages,
            default_webinar_datetime,
        )

        webinar_at = default_webinar_datetime(self.settings.timezone)
        webinar = await self.create_record(
            "webinars",
            {
                "slug": "laranko-remont-bez-haosu-2026-05-20",
                "title": WEBINAR_TITLE,
                "description": WELCOME_TEXT,
                "confirmation_text": CONFIRMATION_TEXT,
                "scheduled_at": webinar_at.isoformat(),
                "timezone": self.settings.timezone,
                "status": "published",
                "zoom_url": self.settings.default_zoom_url,
                "course_url": self.settings.default_course_url,
                "instagram_ola_url": self.settings.instagram_ola_url,
                "instagram_school_url": self.settings.instagram_school_url,
                "instagram_studio_url": self.settings.instagram_studio_url,
                "curator_username": self.settings.curator_username,
            },
        )
        for template in default_scheduled_messages(webinar_at):
            await self.create_record(
                "scheduled_messages",
                {
                    "webinar": webinar["id"],
                    "title": template.title,
                    "text": template.text,
                    "send_at": template.send_at.isoformat(),
                    "buttons": [button.__dict__ for button in template.buttons],
                    "media_type": template.media_type,
                    "media_file_id": "",
                    "media_file_ids": [],
                    "status": "pending",
                    "sent_at": "",
                },
            )

    async def list_records(
        self,
        collection: str,
        *,
        filter_: str | None = None,
        sort: str | None = None,
        page: int = 1,
        per_page: int = 50,
        expand: str | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"page": page, "perPage": per_page}
        if filter_:
            params["filter"] = filter_
        if sort:
            params["sort"] = sort
        if expand:
            params["expand"] = expand
        data = await self._request("GET", f"/api/collections/{collection}/records", params=params)
        return data.get("items", [])

    async def list_all_records(
        self,
        collection: str,
        *,
        filter_: str | None = None,
        sort: str | None = None,
        expand: str | None = None,
    ) -> list[dict[str, Any]]:
        page = 1
        items: list[dict[str, Any]] = []
        while True:
            batch = await self.list_records(
                collection,
                filter_=filter_,
                sort=sort,
                page=page,
                per_page=200,
                expand=expand,
            )
            items.extend(batch)
            if len(batch) < 200:
                return items
            page += 1

    async def create_record(self, collection: str, data: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", f"/api/collections/{collection}/records", json=data)

    async def get_record(self, collection: str, record_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/api/collections/{collection}/records/{record_id}")

    async def update_record(self, collection: str, record_id: str, data: dict[str, Any]) -> dict[str, Any]:
        return await self._request(
            "PATCH",
            f"/api/collections/{collection}/records/{record_id}",
            json=data,
        )

    async def upsert_user(self, tg_user: Any) -> dict[str, Any]:
        telegram_id = str(tg_user.id)
        users = await self.list_records(USER_COLLECTION, filter_=f'telegram_id="{telegram_id}"', per_page=1)
        payload = {
            "telegram_id": telegram_id,
            "username": tg_user.username or "",
            "first_name": tg_user.first_name or "",
            "last_name": tg_user.last_name or "",
            "language_code": tg_user.language_code or "",
            "last_seen_at": datetime.now(timezone.utc).isoformat(),
        }
        if users:
            return await self.update_record(USER_COLLECTION, users[0]["id"], payload)
        payload["first_seen_at"] = payload["last_seen_at"]
        return await self.create_record(USER_COLLECTION, payload)

    async def attribution_by_token(self, token: str) -> dict[str, Any] | None:
        if not token:
            return None
        items = await self.list_records("attribution_tokens", filter_=f'token="{token}"', per_page=1)
        return items[0] if items else None

    async def mark_attribution_started(
        self,
        attribution: dict[str, Any],
        *,
        user_id: str,
        telegram_id: int | str,
        event_id: str,
    ) -> dict[str, Any]:
        return await self.update_record(
            "attribution_tokens",
            attribution["id"],
            {
                "user": user_id,
                "telegram_id": str(telegram_id),
                "status": "started",
                "started_at": datetime.now(timezone.utc).isoformat(),
                "start_event_id": event_id,
            },
        )

    async def latest_started_attribution_for_user(self, user_id: str) -> dict[str, Any] | None:
        items = await self.list_records(
            "attribution_tokens",
            filter_=f'user="{user_id}" && status!="registered"',
            sort="-started_at",
            per_page=1,
        )
        return items[0] if items else None

    async def mark_attribution_registered(self, attribution: dict[str, Any], *, event_id: str) -> dict[str, Any]:
        return await self.update_record(
            "attribution_tokens",
            attribution["id"],
            {
                "status": "registered",
                "registered_at": datetime.now(timezone.utc).isoformat(),
                "registration_event_id": event_id,
            },
        )

    async def active_webinar(self) -> dict[str, Any]:
        webinars = await self.list_records(
            "webinars",
            filter_='status="published"',
            sort="scheduled_at",
            per_page=1,
        )
        if not webinars:
            raise PocketBaseError("No published webinars found")
        return webinars[0]

    async def registration_for(self, user_id: str, webinar_id: str) -> dict[str, Any] | None:
        registrations = await self.list_records(
            "registrations",
            filter_=f'user="{user_id}" && webinar="{webinar_id}"',
            per_page=1,
        )
        return registrations[0] if registrations else None

    async def save_registration(
        self,
        *,
        user_id: str,
        webinar_id: str,
        answers: dict[str, Any],
    ) -> dict[str, Any]:
        payload = {
            "user": user_id,
            "webinar": webinar_id,
            "name": answers.get("name", ""),
            "phone": answers.get("phone", ""),
            "answers": answers,
            "status": "registered",
            "registered_at": datetime.now(timezone.utc).isoformat(),
        }
        existing = await self.registration_for(user_id, webinar_id)
        if existing:
            return await self.update_record("registrations", existing["id"], payload)
        return await self.create_record("registrations", payload)

    async def pending_messages(self, now: datetime) -> list[dict[str, Any]]:
        now_filter = format_pocketbase_datetime(now)
        return await self.list_all_records(
            "scheduled_messages",
            filter_=f'status="pending" && send_at<="{now_filter}"',
            sort="send_at",
        )

    async def registered_users_for_webinar(self, webinar_id: str) -> list[dict[str, Any]]:
        registrations = await self.list_all_records(
            "registrations",
            filter_=f'webinar="{webinar_id}" && status="registered"',
        )
        for registration in registrations:
            try:
                registration["user_record"] = await self.get_record(USER_COLLECTION, registration["user"])
            except PocketBaseError:
                registration["user_record"] = {}
        return registrations

    async def log_broadcast(self, data: dict[str, Any]) -> dict[str, Any]:
        return await self.create_record("broadcast_logs", data)

    async def registrations_csv(self) -> bytes:
        registrations = await self.list_all_records("registrations", sort="-registered_at")
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "registered_at",
                "webinar",
                "telegram_id",
                "username",
                "name",
                "phone",
                "design_stage",
                "realization_experience",
                "speaker_question",
            ]
        )
        user_cache: dict[str, dict[str, Any]] = {}
        webinar_cache: dict[str, dict[str, Any]] = {}
        for item in registrations:
            user_id = item.get("user", "")
            webinar_id = item.get("webinar", "")
            if user_id and user_id not in user_cache:
                user_cache[user_id] = await self.get_record(USER_COLLECTION, user_id)
            if webinar_id and webinar_id not in webinar_cache:
                webinar_cache[webinar_id] = await self.get_record("webinars", webinar_id)
            user = user_cache.get(user_id, {})
            webinar = webinar_cache.get(webinar_id, {})
            answers = item.get("answers") or {}
            if isinstance(answers, str):
                answers = json.loads(answers)
            writer.writerow(
                [
                    item.get("registered_at", ""),
                    webinar.get("title", ""),
                    user.get("telegram_id", ""),
                    user.get("username", ""),
                    item.get("name", ""),
                    item.get("phone", ""),
                    answers.get("design_stage", ""),
                    answers.get("realization_experience", ""),
                    answers.get("speaker_question", ""),
                ]
            )
        return output.getvalue().encode("utf-8-sig")


def collection_definitions() -> list[dict[str, Any]]:
    definitions = [
        {
            "name": USER_COLLECTION,
            "type": "base",
            "system": False,
            "schema": [
                {"name": "telegram_id", "type": "text", "required": True, "options": {"maxSize": 64}},
                {"name": "username", "type": "text", "required": False, "options": {}},
                {"name": "first_name", "type": "text", "required": False, "options": {}},
                {"name": "last_name", "type": "text", "required": False, "options": {}},
                {"name": "language_code", "type": "text", "required": False, "options": {}},
                {"name": "first_seen_at", "type": "date", "required": False, "options": {}},
                {"name": "last_seen_at", "type": "date", "required": False, "options": {}},
            ],
            "indexes": ["CREATE UNIQUE INDEX idx_tg_users_telegram_id ON tg_users (telegram_id)"],
        },
        {
            "name": "webinars",
            "type": "base",
            "system": False,
            "schema": [
                {"name": "slug", "type": "text", "required": True, "options": {}},
                {"name": "title", "type": "text", "required": True, "options": {}},
                {"name": "description", "type": "text", "required": False, "options": {}},
                {"name": "confirmation_text", "type": "text", "required": False, "options": {}},
                {"name": "scheduled_at", "type": "date", "required": True, "options": {}},
                {"name": "timezone", "type": "text", "required": True, "options": {}},
                {"name": "status", "type": "select", "required": True, "options": {"maxSelect": 1, "values": ["draft", "published", "archived"]}},
                {"name": "zoom_url", "type": "url", "required": False, "options": {}},
                {"name": "course_url", "type": "url", "required": False, "options": {}},
                {"name": "instagram_ola_url", "type": "url", "required": False, "options": {}},
                {"name": "instagram_school_url", "type": "url", "required": False, "options": {}},
                {"name": "instagram_studio_url", "type": "url", "required": False, "options": {}},
                {"name": "curator_username", "type": "text", "required": False, "options": {}},
            ],
            "indexes": ["CREATE UNIQUE INDEX idx_webinars_slug ON webinars (slug)"],
        },
        {
            "name": "registrations",
            "type": "base",
            "system": False,
            "schema": [
                {"name": "user", "type": "text", "required": True, "options": {}},
                {"name": "webinar", "type": "text", "required": True, "options": {}},
                {"name": "name", "type": "text", "required": True, "options": {}},
                {"name": "phone", "type": "text", "required": True, "options": {}},
                {"name": "answers", "type": "json", "required": False, "options": {}},
                {"name": "status", "type": "select", "required": True, "options": {"maxSelect": 1, "values": ["registered", "cancelled"]}},
                {"name": "registered_at", "type": "date", "required": False, "options": {}},
            ],
            "indexes": [],
        },
        {
            "name": "scheduled_messages",
            "type": "base",
            "system": False,
            "schema": [
                {"name": "webinar", "type": "text", "required": True, "options": {}},
                {"name": "title", "type": "text", "required": True, "options": {}},
                {"name": "text", "type": "text", "required": True, "options": {}},
                {"name": "send_at", "type": "date", "required": True, "options": {}},
                {"name": "buttons", "type": "json", "required": False, "options": {}},
                {"name": "media_type", "type": "select", "required": True, "options": {"maxSelect": 1, "values": ["none", "photo", "video"]}},
                {"name": "media_file_id", "type": "text", "required": False, "options": {}},
                {"name": "media_file_ids", "type": "json", "required": False, "options": {}},
                {"name": "status", "type": "select", "required": True, "options": {"maxSelect": 1, "values": ["pending", "sending", "sent", "failed"]}},
                {"name": "sent_at", "type": "date", "required": False, "options": {}},
            ],
            "indexes": [],
        },
        {
            "name": "attribution_tokens",
            "type": "base",
            "system": False,
            "schema": [
                {"name": "token", "type": "text", "required": True, "options": {"maxSize": 64}},
                {"name": "pixel_id", "type": "text", "required": False, "options": {}},
                {"name": "fbclid", "type": "text", "required": False, "options": {}},
                {"name": "fbc", "type": "text", "required": False, "options": {}},
                {"name": "fbp", "type": "text", "required": False, "options": {}},
                {"name": "utm", "type": "json", "required": False, "options": {}},
                {"name": "source_url", "type": "text", "required": False, "options": {"maxSize": 5000}},
                {"name": "referrer", "type": "text", "required": False, "options": {"maxSize": 5000}},
                {"name": "user_agent", "type": "text", "required": False, "options": {"maxSize": 2000}},
                {"name": "ip_address", "type": "text", "required": False, "options": {}},
                {"name": "telegram_id", "type": "text", "required": False, "options": {}},
                {"name": "user", "type": "text", "required": False, "options": {}},
                {"name": "status", "type": "select", "required": True, "options": {"maxSelect": 1, "values": ["created", "started", "registered"]}},
                {"name": "start_event_id", "type": "text", "required": False, "options": {}},
                {"name": "registration_event_id", "type": "text", "required": False, "options": {}},
                {"name": "created_at", "type": "date", "required": True, "options": {}},
                {"name": "started_at", "type": "date", "required": False, "options": {}},
                {"name": "registered_at", "type": "date", "required": False, "options": {}},
            ],
            "indexes": ["CREATE UNIQUE INDEX idx_attribution_tokens_token ON attribution_tokens (token)"],
        },
        {
            "name": "broadcast_logs",
            "type": "base",
            "system": False,
            "schema": [
                {"name": "scheduled_message", "type": "text", "required": False, "options": {}},
                {"name": "webinar", "type": "text", "required": False, "options": {}},
                {"name": "recipient_count", "type": "number", "required": False, "options": {"noDecimal": True}},
                {"name": "success_count", "type": "number", "required": False, "options": {"noDecimal": True}},
                {"name": "failure_count", "type": "number", "required": False, "options": {"noDecimal": True}},
                {"name": "errors", "type": "json", "required": False, "options": {}},
                {"name": "sent_at", "type": "date", "required": True, "options": {}},
            ],
            "indexes": [],
        },
    ]
    for collection in definitions:
        for field in collection["schema"]:
            if field["type"] == "text":
                field.setdefault("options", {})
                field["options"].setdefault("maxSize", 2000)
            if field["type"] == "json":
                field.setdefault("options", {})
                field["options"].setdefault("maxSize", 200000)
    return definitions


def format_pocketbase_datetime(value: datetime) -> str:
    value = value.astimezone(timezone.utc)
    milliseconds = value.microsecond // 1000
    return value.strftime(f"%Y-%m-%d %H:%M:%S.{milliseconds:03d}Z")
