from app.handlers_admin import media_label, parse_admin_datetime


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
    assert media_label({"media_type": "video", "media_file_id": ""}) == "не прикріплено"
    assert media_label({"media_type": "photo", "media_file_id": "abc"}) == "1 фото прикріплено"
    assert media_label({"media_type": "photo", "media_file_ids": ["a", "b"]}) == "2 фото прикріплено"
