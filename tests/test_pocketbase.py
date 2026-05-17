from app.pocketbase import collection_definitions


def test_collection_definitions_include_required_collections() -> None:
    names = {collection["name"] for collection in collection_definitions()}

    assert names == {
        "tg_users",
        "webinars",
        "registrations",
        "scheduled_messages",
        "attribution_tokens",
        "broadcast_logs",
    }


def test_registrations_store_answers_as_json() -> None:
    registrations = next(
        collection for collection in collection_definitions() if collection["name"] == "registrations"
    )
    fields = {field["name"]: field for field in registrations["schema"]}

    assert fields["answers"]["type"] == "json"
    assert fields["phone"]["required"] is True


def test_scheduled_messages_store_multiple_media_file_ids() -> None:
    scheduled_messages = next(
        collection for collection in collection_definitions() if collection["name"] == "scheduled_messages"
    )
    fields = {field["name"]: field for field in scheduled_messages["schema"]}

    assert fields["media_file_ids"]["type"] == "json"


def test_attribution_tokens_store_meta_click_context() -> None:
    attribution_tokens = next(
        collection for collection in collection_definitions() if collection["name"] == "attribution_tokens"
    )
    fields = {field["name"]: field for field in attribution_tokens["schema"]}

    assert fields["token"]["required"] is True
    assert fields["pixel_id"]["type"] == "text"
    assert fields["fbclid"]["type"] == "text"
    assert fields["fbp"]["type"] == "text"
    assert fields["utm"]["type"] == "json"


def test_broadcast_log_counts_allow_zero_values() -> None:
    broadcast_logs = next(
        collection for collection in collection_definitions() if collection["name"] == "broadcast_logs"
    )
    fields = {field["name"]: field for field in broadcast_logs["schema"]}

    assert fields["failure_count"]["required"] is False
