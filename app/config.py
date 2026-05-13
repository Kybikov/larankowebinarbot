from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    bot_token: str
    admin_ids: tuple[int, ...]
    pocketbase_url: str
    pocketbase_admin_email: str
    pocketbase_admin_password: str
    timezone: str
    default_zoom_url: str
    default_course_url: str
    instagram_ola_url: str
    instagram_school_url: str
    instagram_studio_url: str
    curator_username: str
    bot_username: str
    attribution_host: str
    attribution_port: int
    attribution_public_base_url: str
    meta_pixel_id: str
    meta_access_token: str
    meta_action_source: str

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        bot_token = _required("BOT_TOKEN")
        return cls(
            bot_token=bot_token,
            admin_ids=_parse_admin_ids(os.getenv("ADMIN_IDS", "")),
            pocketbase_url=os.getenv("POCKETBASE_URL", "http://127.0.0.1:8090").rstrip("/"),
            pocketbase_admin_email=_required("POCKETBASE_ADMIN_EMAIL"),
            pocketbase_admin_password=_required("POCKETBASE_ADMIN_PASSWORD"),
            timezone=os.getenv("TIMEZONE", "Europe/Kyiv"),
            default_zoom_url=os.getenv("DEFAULT_ZOOM_URL", "https://example.com/zoom"),
            default_course_url=os.getenv(
                "DEFAULT_COURSE_URL",
                "https://course-laranko.kwiga.com/courses/dizain-bez-khaosu",
            ),
            instagram_ola_url=os.getenv("INSTAGRAM_OLA_URL", "https://www.instagram.com/oolachka"),
            instagram_school_url=os.getenv(
                "INSTAGRAM_SCHOOL_URL", "https://www.instagram.com/laranko_study"
            ),
            instagram_studio_url=os.getenv(
                "INSTAGRAM_STUDIO_URL", "https://www.instagram.com/laranko_interior"
            ),
            curator_username=os.getenv("CURATOR_USERNAME", "Laranko_Academy").lstrip("@"),
            bot_username=os.getenv("BOT_USERNAME", "larankowebirnar_bot").lstrip("@"),
            attribution_host=os.getenv("ATTRIBUTION_HOST", "0.0.0.0"),
            attribution_port=int(os.getenv("ATTRIBUTION_PORT", "8080")),
            attribution_public_base_url=os.getenv("ATTRIBUTION_PUBLIC_BASE_URL", "").rstrip("/"),
            meta_pixel_id=os.getenv("META_PIXEL_ID", "").strip(),
            meta_access_token=os.getenv("META_ACCESS_TOKEN", "").strip(),
            meta_action_source=os.getenv("META_ACTION_SOURCE", "website").strip(),
        )


def _required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Environment variable {name} is required")
    return value


def _parse_admin_ids(raw: str) -> tuple[int, ...]:
    ids: list[int] = []
    for item in raw.replace(";", ",").split(","):
        item = item.strip()
        if item:
            ids.append(int(item))
    if not ids:
        raise RuntimeError("ADMIN_IDS must contain at least one Telegram user id")
    return tuple(ids)
