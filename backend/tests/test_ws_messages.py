import json
import re
from pathlib import Path
from typing import get_args

import pytest
from pydantic import ValidationError

from app.api.schemas import MAX_ANSWER_CHARS
from app.api.ws_messages import (
    Auth,
    EndSession,
    ErrorCode,
    ErrorMessage,
    ServerMessage,
    TextAnswer,
    Transcript,
    parse_client_message,
)

TYPESCRIPT_FILE = Path(__file__).parents[2] / "frontend" / "lib" / "wsMessages.ts"


def test_parses_each_client_message():
    assert parse_client_message('{"type": "auth", "token": "abc"}') == Auth(
        type="auth", token="abc"
    )
    assert parse_client_message('{"type": "text_answer", "text": "hi"}') == TextAnswer(
        type="text_answer", text="hi"
    )
    assert parse_client_message('{"type": "end_session"}') == EndSession(type="end_session")


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        "{}",  # no type
        '{"type": "hack"}',  # unknown type
        '{"type": "auth"}',  # missing field
        '{"type": "end_session", "extra": 1}',  # a field we don't understand
        '{"type": "transcript", "turn_index": 1, "text": "hi"}',  # a server message
    ],
)
def test_rejects_bad_client_messages(raw):
    with pytest.raises(ValidationError):
        parse_client_message(raw)


def test_rejects_text_answer_over_the_limit():
    raw = json.dumps({"type": "text_answer", "text": "x" * (MAX_ANSWER_CHARS + 1)})
    with pytest.raises(ValidationError):
        parse_client_message(raw)


def test_server_messages_carry_their_type():
    """The frontend chooses how to read a message by "type", so it must be in the JSON."""
    sent = json.loads(Transcript(turn_index=1, text="hi").model_dump_json())
    assert sent == {"type": "transcript", "turn_index": 1, "text": "hi"}


def test_error_code_must_be_a_known_code():
    with pytest.raises(ValidationError):
        ErrorMessage(code="oops", message="Something went wrong")


def typescript_messages() -> dict[str, set[str]]:
    """{message type: its field names} for each `{ type: "..."; ... }` in wsMessages.ts."""
    source = re.sub(r"//.*", "", TYPESCRIPT_FILE.read_text(encoding="utf-8"))
    blocks = re.findall(r'\{\s*type:\s*"(\w+)";?([^}]*)\}', source)
    return {name: set(re.findall(r"(\w+)\??:", fields)) | {"type"} for name, fields in blocks}


def python_models():
    """Every message model on both directions."""
    client = [Auth, TextAnswer, EndSession]
    return client + list(get_args(ServerMessage))


def test_typescript_has_the_same_messages_as_python():
    """If a message or field changes on one side only, this fails instead of the browser."""
    python = {
        get_args(model.model_fields["type"].annotation)[0]: set(model.model_fields)
        for model in python_models()
    }
    assert typescript_messages() == python


def test_typescript_has_the_same_error_codes_as_python():
    source = TYPESCRIPT_FILE.read_text(encoding="utf-8")
    union = re.search(r"type ErrorCode =([^;]*);", source).group(1)
    assert set(re.findall(r'"(\w+)"', union)) == set(get_args(ErrorCode))
