from datetime import datetime
from zoneinfo import ZoneInfo

from app.content import REGISTRATION_QUESTIONS, default_scheduled_messages


def test_registration_questions_match_required_flow() -> None:
    assert [question["key"] for question in REGISTRATION_QUESTIONS] == [
        "name",
        "phone",
        "design_stage",
        "realization_experience",
        "speaker_question",
    ]


def test_default_schedule_has_reminders_and_sales_messages() -> None:
    webinar_at = datetime(2026, 5, 20, 18, 0, tzinfo=ZoneInfo("Europe/Kyiv"))

    messages = default_scheduled_messages(webinar_at)

    assert len(messages) >= 10
    assert any(message.send_at == webinar_at.replace(hour=9) for message in messages)
    assert any(message.send_at == webinar_at.replace(hour=17) for message in messages)
    assert any(message.send_at == webinar_at.replace(hour=17, minute=57) for message in messages)
    assert any("спецпропозиція" in message.title.lower() for message in messages)
