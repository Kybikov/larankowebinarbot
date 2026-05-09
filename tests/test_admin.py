from app.handlers_admin import parse_admin_datetime


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
