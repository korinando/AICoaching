"""S3AudioStorage against the real SeaweedFS container, in the ai-coach-test bucket."""

from uuid import uuid4

import pytest

from app.core.config import get_settings
from app.speech.storage import S3AudioStorage, StorageError, new_audio_key

TEST_BUCKET = "ai-coach-test"


def make_storage(**overrides) -> S3AudioStorage:
    settings = get_settings()
    values = {
        "endpoint_url": settings.s3_endpoint_url,
        "access_key": settings.s3_access_key.get_secret_value(),
        "secret_key": settings.s3_secret_key.get_secret_value(),
        "bucket": TEST_BUCKET,
    }
    return S3AudioStorage(**(values | overrides))


def test_saved_file_can_be_read_back():
    storage = make_storage()
    key = f"tests/{uuid4().hex}.wav"
    data = b"RIFF pretend wav bytes"

    storage.save(key, data, "audio/wav")

    try:
        stored = storage.client.get_object(Bucket=TEST_BUCKET, Key=key)
        assert stored["Body"].read() == data
        assert stored["ContentType"] == "audio/wav"
    finally:
        storage.client.delete_object(Bucket=TEST_BUCKET, Key=key)


def test_load_returns_what_was_saved():
    storage = make_storage()
    key = f"tests/{uuid4().hex}.wav"

    storage.save(key, b"some audio", "audio/wav")

    try:
        assert storage.load(key) == b"some audio"
    finally:
        storage.client.delete_object(Bucket=TEST_BUCKET, Key=key)


def test_loading_a_missing_file_is_a_storage_error():
    with pytest.raises(StorageError):
        make_storage().load(f"tests/{uuid4().hex}.wav")


def test_wrong_secret_key_is_refused():
    """Without this, anything on this PC could write to the storage."""
    storage = make_storage(secret_key="not-the-real-secret")

    with pytest.raises(StorageError):
        storage.save(f"tests/{uuid4().hex}.wav", b"data", "audio/wav")


def test_unreachable_server_is_a_storage_error():
    """Port 1: nothing listens there, like the storage container being stopped."""
    storage = make_storage(endpoint_url="http://127.0.0.1:1")

    with pytest.raises(StorageError):
        storage.save(f"tests/{uuid4().hex}.wav", b"data", "audio/wav")


def test_new_keys_are_unique_and_named_after_the_session():
    first, second = new_audio_key(7), new_audio_key(7)
    assert first != second
    assert first.startswith("sessions/7/")
