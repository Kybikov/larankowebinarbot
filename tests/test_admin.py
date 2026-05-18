from app.handlers_admin import format_admin_user_row, latest_registration_by_user, media_label, parse_admin_datetime


def test_parse_admin_datetime_accepts_human_ukrainian_format() -> None:
    parsed = parse_admin_datetime("20.05.2026 18:00")

    assert parsed.year == 2026
    assert parsed.month == 5
    assert parsed.day == 20
    assert parsed.hour == 18
    assert parsed.minute == 0


def test_parse_admin_datetime_keeps_iso_like_format() -> None:
    parsed = parse_admin_datetime("2026-05-20 18:00")

    assert parsed.year == 2026
    assert parsed.month == 5
    assert parsed.day == 20


def test_media_label_requires_file_id() -> None:
    assert media_label({"media_type": "video", "media_file_id": ""}) == "\u043d\u0435 \u043f\u0440\u0438\u043a\u0440\u0456\u043f\u043b\u0435\u043d\u043e"
    assert media_label({"media_type": "photo", "media_file_id": "abc"}) == "1 \u0444\u043e\u0442\u043e \u043f\u0440\u0438\u043a\u0440\u0456\u043f\u043b\u0435\u043d\u043e"
    assert media_label({"media_type": "photo", "media_file_ids": ["a", "b"]}) == "2 \u0444\u043e\u0442\u043e \u043f\u0440\u0438\u043a\u0440\u0456\u043f\u043b\u0435\u043d\u043e"


def test_latest_registration_by_user_keeps_latest_sorted_item() -> None:
    registrations = [
        {"id": "new", "user": "u1", "registered_at": "2026-05-18 10:00:00.000Z"},
        {"id": "old", "user": "u1", "registered_at": "2026-05-17 10:00:00.000Z"},
        {"id": "other", "user": "u2", "registered_at": "2026-05-17 11:00:00.000Z"},
    ]

    result = latest_registration_by_user(registrations)

    assert result["u1"]["id"] == "new"
    assert result["u2"]["id"] == "other"


def test_format_admin_user_row_marks_registration_status() -> None:
    user = {
        "id": "u1",
        "telegram_id": "123",
        "username": "test_user",
        "first_name": "Test",
        "last_name": "User",
        "language_code": "uk",
        "last_seen_at": "2026-05-18 10:00:00.000Z",
    }
    registration = {
        "user": "u1",
        "name": "Test",
        "phone": "+380",
        "registered_at": "2026-05-18 10:05:00.000Z",
    }

    registered = format_admin_user_row(1, user, registration, "Europe/Kyiv")
    unregistered = format_admin_user_row(1, user, None, "Europe/Kyiv")

    assert "\u2705" in registered
    assert "\u274c" in unregistered
    assert "<code>123</code>" in registered
