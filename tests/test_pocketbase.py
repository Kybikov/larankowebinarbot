from app.pocketbase import collection_definitions


def test_collection_definitions_include_required_collections() -> None:
    names = {collection["name"] for collection in collection_definitions()}

    assert names == {
        "tg_users",
        "webinars",
        "registrations",
        "scheduled_messages",
        "broadcast_logs",
    }


def test_registrations_store_answers_as_json() -> None:
    registrations = next(
        collection for collection in collection_definitions() if collection["name"] == "registrations"
    )
    fields = {field["name"]: field for field in registrations["schema"]}

    assert fields["answers"]["type"] == "json"
    assert fields["phone"]["required"] is True
