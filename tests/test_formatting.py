from app.formatting import format_datetime_with_tz


def test_format_datetime_with_tz_converts_pocketbase_utc_to_kyiv() -> None:
    assert format_datetime_with_tz("2026-05-09 15:57:30.481Z") == "09.05.2026 о 18:57 за Києвом"


def test_format_datetime_with_tz_handles_empty_value() -> None:
    assert format_datetime_with_tz("") == "-"
