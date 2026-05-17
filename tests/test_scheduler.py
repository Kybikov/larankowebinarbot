from datetime import datetime, timezone

from app.scheduler import is_due, parse_pocketbase_datetime


def test_parse_pocketbase_datetime_handles_zulu_dates() -> None:
    parsed = parse_pocketbase_datetime("2026-05-17 15:00:00.000Z")

    assert parsed == datetime(2026, 5, 17, 15, 0, tzinfo=timezone.utc)


def test_is_due_rejects_future_messages() -> None:
    now = datetime(2026, 5, 17, 12, 30, tzinfo=timezone.utc)

    assert is_due({"send_at": "2026-05-17 15:00:00.000Z"}, now) is False
    assert is_due({"send_at": "2026-05-17 12:00:00.000Z"}, now) is True
