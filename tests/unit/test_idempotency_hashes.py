from prd_engine.api.middleware.idempotency import hash_key, hash_request


def test_hash_request_is_stable_for_equivalent_json_objects():
    first = {"name": "workflow", "payload": {"b": 2, "a": 1}}
    second = {"payload": {"a": 1, "b": 2}, "name": "workflow"}

    assert hash_request(first) == hash_request(second)


def test_hash_request_changes_when_payload_changes():
    first = {"workflow": "prd_processing", "priority": 3}
    second = {"workflow": "prd_processing", "priority": 4}

    assert hash_request(first) != hash_request(second)


def test_idempotency_key_hash_does_not_store_plain_key():
    raw_key = "client-request-unique-key"

    assert hash_key(raw_key) != raw_key
    assert len(hash_key(raw_key)) == 64
