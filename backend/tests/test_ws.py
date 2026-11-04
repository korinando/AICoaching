"""The live interview WebSocket /ws/sessions/{id} (Week 4 Step 2)."""

import base64
import io
import threading
import wave
from datetime import timedelta

import pytest
from starlette.websockets import WebSocketDisconnect

from app.agent.interviewer import CLOSING_TEXT, REPEAT_TEXT
from app.agent.llm_client import LLMError
from app.api import ws as ws_api
from app.api.deps import get_speech_to_text
from app.api.schemas import MAX_ANSWER_CHARS
from app.core.security import create_token
from app.main import app
from app.models import InterviewSession, Turn, User
from app.services import recordings
from app.speech.storage import StorageError
from app.speech.stt import SpeechToTextError
from app.speech.tts import TextToSpeechError
from tests.fakes import ANSWER, FakeSpeechToText, decision, spoken, streamed

REPLY = "Why would you add it?"


@pytest.fixture(autouse=True)
def speech(client) -> FakeSpeechToText:
    fake = FakeSpeechToText()
    app.dependency_overrides[get_speech_to_text] = lambda: fake
    return fake


@pytest.fixture
def session_id(client, auth_headers, fake_llm, template, storage) -> int:
    fake_llm.script.append(decision("next_question", text="Welcome! What is REST?"))
    response = client.post("/sessions", json={"template_id": template.id}, headers=auth_headers)
    storage.files.clear()  # forget the opening question's audio: tests count what they cause
    return response.json()["id"]


@pytest.fixture
def token(user) -> str:
    return create_token(user.id, "access")


def connect(client, session_id):
    return client.websocket_connect(f"/ws/sessions/{session_id}")


def login(socket, token):
    socket.send_json({"type": "auth", "token": token})


def messages_of_one_reply(socket) -> list[dict]:
    """All messages of one reply, up to turn_complete, or an error so a failing test can't hang."""
    messages = []
    while not messages or messages[-1]["type"] not in ("turn_complete", "error"):
        messages.append(socket.receive_json())
    return messages


def assert_refused(socket, code: str, close_code: int):
    assert socket.receive_json()["code"] == code
    with pytest.raises(WebSocketDisconnect) as closed:
        socket.receive_json()
    assert closed.value.code == close_code


def turns_in(db, session_id) -> list[Turn]:
    return db.get(InterviewSession, session_id).turns


# --- Logging in --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "first_frame",
    [
        {"text": '{"type": "auth", "token": "not-a-token"}'},
        {"text": "not json"},
        {"text": '{"type": "end_session"}'},  # anything else before auth
        {"bytes": b"audio before logging in"},
    ],
)
def test_bad_first_frame_is_refused(client, session_id, fake_llm, first_frame):
    with connect(client, session_id) as socket:
        socket.send(
            {
                "type": "websocket.receive",
                "text": first_frame.get("text"),
                "bytes": first_frame.get("bytes"),
            }
        )
        assert_refused(socket, "unauthorized", ws_api.CLOSE_UNAUTHORIZED)


def test_refresh_token_is_refused(client, session_id, user):
    with connect(client, session_id) as socket:
        login(socket, create_token(user.id, "refresh"))
        assert_refused(socket, "unauthorized", ws_api.CLOSE_UNAUTHORIZED)


def test_expired_token_is_refused(client, session_id, user):
    with connect(client, session_id) as socket:
        login(socket, create_token(user.id, "access", expires_in=timedelta(seconds=-1)))
        assert_refused(socket, "unauthorized", ws_api.CLOSE_UNAUTHORIZED)


def test_silent_connection_is_closed_after_the_timeout(client, session_id, monkeypatch):
    monkeypatch.setattr(ws_api, "AUTH_TIMEOUT_SECONDS", 0.01)

    with connect(client, session_id) as socket:
        assert_refused(socket, "unauthorized", ws_api.CLOSE_UNAUTHORIZED)


def test_other_users_session_looks_like_a_missing_one(client, db, session_id, token):
    other = User(email="other@example.com", password_hash="x", name="Other")
    db.add(other)
    db.flush()

    with connect(client, session_id) as socket:
        login(socket, create_token(other.id, "access"))
        assert_refused(socket, "not_found", ws_api.CLOSE_NOT_FOUND)
    with connect(client, 999_999) as socket:
        login(socket, token)
        assert_refused(socket, "not_found", ws_api.CLOSE_NOT_FOUND)


# --- Answering ---------------------------------------------------------------------------------


def test_typed_answer_gets_the_reply_in_order(client, db, session_id, token, fake_llm, tts):
    fake_llm.script.append(streamed("follow_up", REPLY))

    with connect(client, session_id) as socket:
        login(socket, token)
        socket.send_json({"type": "text_answer", "text": ANSWER})
        messages = messages_of_one_reply(socket)

    assert [m["type"] for m in messages] == [
        "transcript",
        "interviewer_text",
        "audio_chunk",
        "turn_complete",
    ]
    assert messages[0] == {"type": "transcript", "turn_index": 1, "text": ANSWER}
    assert messages[1] == {"type": "interviewer_text", "turn_index": 2, "seq": 0, "text": REPLY}
    assert messages[2]["seq"] == 0
    assert base64.b64decode(messages[2]["audio_base64"]) == spoken(REPLY)

    _opening, saved_answer, reply = turns_in(db, session_id)
    assert saved_answer.text == ANSWER
    assert reply.total_latency_ms is not None
    assert reply.llm_ms is not None


def test_recording_gets_the_reply(client, db, session_id, token, fake_llm, audio_samples, storage):
    fake_llm.script.append(streamed("follow_up", REPLY))

    with connect(client, session_id) as socket:
        login(socket, token)
        socket.send_bytes(audio_samples["webm"])
        messages = messages_of_one_reply(socket)

    assert messages[0] == {"type": "transcript", "turn_index": 1, "text": ANSWER}
    assert messages[1]["text"] == REPLY
    _opening, saved_answer, reply = turns_in(db, session_id)
    assert saved_answer.audio_url in storage.files
    assert reply.stt_ms is not None


def test_several_answers_on_one_connection(client, session_id, token, fake_llm):
    fake_llm.script.extend([streamed("follow_up"), streamed("follow_up")])

    with connect(client, session_id) as socket:
        login(socket, token)
        for expected_reply_turn in (2, 4):
            socket.send_json({"type": "text_answer", "text": ANSWER})
            assert messages_of_one_reply(socket)[-1]["turn_index"] == expected_reply_turn


def test_voice_failure_still_sends_the_text(client, session_id, token, fake_llm, tts):
    tts.error = TextToSpeechError("voice file missing")
    fake_llm.script.append(streamed("follow_up", REPLY))

    with connect(client, session_id) as socket:
        login(socket, token)
        socket.send_json({"type": "text_answer", "text": ANSWER})
        messages = messages_of_one_reply(socket)

    assert [m["type"] for m in messages] == ["transcript", "interviewer_text", "turn_complete"]


def test_storage_failure_only_loses_the_replay(client, db, session_id, token, fake_llm, storage):
    storage.error = StorageError("connection refused")
    fake_llm.script.append(streamed("follow_up", REPLY))

    with connect(client, session_id) as socket:
        login(socket, token)
        socket.send_json({"type": "text_answer", "text": ANSWER})
        messages = messages_of_one_reply(socket)

    assert "audio_chunk" in [m["type"] for m in messages]
    assert turns_in(db, session_id)[-1].audio_url is None


# --- Messages that can't be handled: an error, and the connection stays open ---------------------


@pytest.mark.parametrize(
    ("setup", "code"),
    [
        (lambda speech, monkeypatch: setattr(speech, "text", ""), "no_speech"),
        (
            lambda speech, monkeypatch: setattr(speech, "error", SpeechToTextError("crashed")),
            "server_error",
        ),
        (
            lambda speech, monkeypatch: monkeypatch.setattr(recordings, "MAX_AUDIO_BYTES", 10),
            "invalid_audio",
        ),
    ],
)
def test_rejected_recording_leaves_the_interview_alone(
    client, db, session_id, token, audio_samples, speech, monkeypatch, setup, code
):
    setup(speech, monkeypatch)

    with connect(client, session_id) as socket:
        login(socket, token)
        socket.send_bytes(audio_samples["webm"])
        assert socket.receive_json()["code"] == code

    assert len(turns_in(db, session_id)) == 1


@pytest.mark.parametrize("sample", ["short_webm", "not_audio"])
def test_unusable_audio_is_invalid_audio(client, session_id, token, audio_samples, sample):
    data = audio_samples.get(sample, b"not really audio" * 100)

    with connect(client, session_id) as socket:
        login(socket, token)
        socket.send_bytes(data)
        assert socket.receive_json()["code"] == "invalid_audio"


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        '{"type": "hack"}',
        '{"type": "auth", "token": "again"}',
        '{"type": "text_answer", "text": "%s"}' % ("x" * (MAX_ANSWER_CHARS + 1)),
    ],
)
def test_bad_message_gets_an_error_and_the_connection_stays_open(
    client, session_id, token, fake_llm, raw
):
    fake_llm.script.append(streamed("follow_up", REPLY))

    with connect(client, session_id) as socket:
        login(socket, token)
        socket.send_text(raw)
        assert socket.receive_json()["code"] == "invalid_message"

        socket.send_json({"type": "text_answer", "text": ANSWER})
        assert messages_of_one_reply(socket)[1]["text"] == REPLY


def test_unexpected_crash_is_a_server_error_and_the_interview_continues(
    client, db, session_id, token, fake_llm, tts
):
    tts.error = RuntimeError("a bug, not a known failure")
    fake_llm.script.extend([streamed("follow_up"), streamed("follow_up", REPLY)])

    with connect(client, session_id) as socket:
        login(socket, token)
        socket.send_json({"type": "text_answer", "text": ANSWER})
        messages = [socket.receive_json() for _ in range(3)]
        assert messages[-1]["code"] == "server_error"
        assert len(turns_in(db, session_id)) == 3  # the answer and reply are still saved

        tts.error = None
        socket.send_json({"type": "text_answer", "text": ANSWER})
        assert messages_of_one_reply(socket)[1]["text"] == REPLY


# --- Ending ------------------------------------------------------------------------------------


def test_end_session_marks_it_abandoned_and_closes(client, db, session_id, token):
    with connect(client, session_id) as socket:
        login(socket, token)
        socket.send_json({"type": "end_session"})
        assert socket.receive_json() == {"type": "session_ended", "status": "abandoned"}
        with pytest.raises(WebSocketDisconnect) as closed:
            socket.receive_json()
        assert closed.value.code == 1000

    session = db.get(InterviewSession, session_id)
    assert session.status == "abandoned"
    assert session.ended_at is not None


def test_agent_finishing_the_interview_ends_the_session(client, db, token, session_id, fake_llm):
    # The last topic: on any other, the agent's rules replace an early "end".
    session = db.get(InterviewSession, session_id)
    session.agent_state = {**session.agent_state, "current_topic_index": 4}
    db.flush()
    fake_llm.script.append(streamed("end", CLOSING_TEXT))

    with connect(client, session_id) as socket:
        login(socket, token)
        socket.send_json({"type": "text_answer", "text": ANSWER})
        messages_of_one_reply(socket)
        assert socket.receive_json() == {"type": "session_ended", "status": "completed"}
        with pytest.raises(WebSocketDisconnect):
            socket.receive_json()

    assert db.get(InterviewSession, session_id).status == "completed"


@pytest.mark.parametrize(
    "send",
    [
        lambda socket: socket.send_json({"type": "text_answer", "text": ANSWER}),
        lambda socket: socket.send_bytes(b"audio"),
        lambda socket: socket.send_json({"type": "end_session"}),
    ],
)
def test_finished_interview_takes_nothing_more(client, db, session_id, token, speech, send):
    db.get(InterviewSession, session_id).status = "completed"
    db.flush()

    with connect(client, session_id) as socket:
        login(socket, token)
        send(socket)
        assert socket.receive_json()["code"] == "interview_closed"

    assert speech.calls == []


# --- Sentence by sentence (Step 5) ---------------------------------------------------------------

FIRST = "This is the first sentence."
SECOND = "This is the second sentence?"
TIMEOUT_S = 5


def audio_seqs(messages) -> list[int]:
    return [m["seq"] for m in messages if m["type"] == "audio_chunk"]


def test_each_sentence_gets_its_own_text_and_voice(client, session_id, token, fake_llm):
    fake_llm.script.append(["ACTION: follow_up\nThis is the fi", f"rst sentence. {SECOND}"])

    with connect(client, session_id) as socket:
        login(socket, token)
        socket.send_json({"type": "text_answer", "text": ANSWER})
        messages = messages_of_one_reply(socket)

    texts = [m for m in messages if m["type"] == "interviewer_text"]
    assert [(m["seq"], m["text"]) for m in texts] == [(0, FIRST), (1, SECOND)]
    chunks = [m for m in messages if m["type"] == "audio_chunk"]
    assert [base64.b64decode(c["audio_base64"]) for c in chunks] == [spoken(FIRST), spoken(SECOND)]


def test_saved_turn_has_the_whole_reply_and_one_voice_file(
    client, db, session_id, token, fake_llm, storage
):
    fake_llm.script.append(streamed("follow_up", f"{FIRST} {SECOND}"))

    with connect(client, session_id) as socket:
        login(socket, token)
        socket.send_json({"type": "text_answer", "text": ANSWER})
        messages_of_one_reply(socket)

    reply = turns_in(db, session_id)[-1]
    assert reply.text == f"{FIRST} {SECOND}"
    with wave.open(io.BytesIO(storage.files[reply.audio_url][0])) as joined:
        assert joined.readframes(joined.getnframes()) == f"{FIRST}{SECOND}".encode()
    assert reply.tts_ms is not None
    assert reply.total_latency_ms is not None
    assert db.get(InterviewSession, session_id).agent_state["follow_ups_on_current"] == 1


def test_voices_run_together_but_arrive_in_order(client, session_id, token, fake_llm, tts):
    """The first voice can't finish until the second has: one at a time, this would time out."""
    second_done = threading.Event()
    speak = tts.synthesize

    def slow_first(text):
        if text == FIRST:
            assert second_done.wait(TIMEOUT_S), "the voices didn't run at the same time"
        result = speak(text)
        if text == SECOND:
            second_done.set()
        return result

    tts.synthesize = slow_first
    fake_llm.script.append(streamed("follow_up", f"{FIRST} {SECOND}"))

    with connect(client, session_id) as socket:
        login(socket, token)
        socket.send_json({"type": "text_answer", "text": ANSWER})
        messages = messages_of_one_reply(socket)

    assert audio_seqs(messages) == [0, 1]


def test_first_voice_is_sent_before_the_reply_has_finished(client, session_id, token, fake_llm):
    """Gemini can't continue until the test has received the first voice."""
    first_voice_arrived = threading.Event()

    def pieces():
        yield f"ACTION: follow_up\n{FIRST} "
        assert first_voice_arrived.wait(TIMEOUT_S), "the voice waited for the whole reply"
        yield SECOND

    fake_llm.script.append(pieces())

    with connect(client, session_id) as socket:
        login(socket, token)
        socket.send_json({"type": "text_answer", "text": ANSWER})
        while (message := socket.receive_json())["type"] != "audio_chunk":
            assert message["type"] in ("transcript", "interviewer_text")
        assert message["seq"] == 0
        first_voice_arrived.set()
        assert messages_of_one_reply(socket)[-1]["type"] == "turn_complete"


def test_one_failed_voice_keeps_the_others_and_their_numbers(
    client, db, session_id, token, fake_llm, tts, storage
):
    speak = tts.synthesize

    def first_fails(text):
        if text == FIRST:
            raise TextToSpeechError("crashed on this text")
        return speak(text)

    tts.synthesize = first_fails
    fake_llm.script.append(streamed("follow_up", f"{FIRST} {SECOND}"))

    with connect(client, session_id) as socket:
        login(socket, token)
        socket.send_json({"type": "text_answer", "text": ANSWER})
        messages = messages_of_one_reply(socket)

    assert [m["seq"] for m in messages if m["type"] == "interviewer_text"] == [0, 1]
    assert audio_seqs(messages) == [1]  # seq still matches its text
    with wave.open(io.BytesIO(storage.files[turns_in(db, session_id)[-1].audio_url][0])) as joined:
        assert joined.readframes(joined.getnframes()) == SECOND.encode()


def test_llm_failure_gives_the_fallback_reply(client, db, session_id, token, fake_llm):
    fake_llm.script.extend([LLMError("first"), LLMError("second")])

    with connect(client, session_id) as socket:
        login(socket, token)
        socket.send_json({"type": "text_answer", "text": ANSWER})
        messages = messages_of_one_reply(socket)

    assert "Let's move on" in messages[1]["text"]
    assert turns_in(db, session_id)[-1].text == messages[1]["text"]


def test_short_answer_gets_the_fixed_reply_with_a_voice(client, db, session_id, token, fake_llm):
    with connect(client, session_id) as socket:
        login(socket, token)
        socket.send_json({"type": "text_answer", "text": "yes"})
        messages = messages_of_one_reply(socket)

    assert messages[1]["text"] == REPEAT_TEXT
    assert audio_seqs(messages) == [0]
    assert len(fake_llm.calls) == 1  # only the opening question reached the LLM
    assert len(turns_in(db, session_id)) == 3


def test_answer_saved_by_another_tab_while_streaming_is_busy(
    client, db, session_id, token, fake_llm
):
    """Both tabs read the same turn number. The second to save is told, and nothing is broken."""

    def pieces():
        yield "ACTION: follow_up\nHi "
        session = db.get(InterviewSession, session_id)
        session.turns.append(Turn(turn_index=1, speaker="candidate", text="From the other tab"))
        db.commit()
        yield "there."

    fake_llm.script.append(pieces())

    with connect(client, session_id) as socket:
        login(socket, token)
        socket.send_json({"type": "text_answer", "text": ANSWER})
        while (message := socket.receive_json())["type"] != "error":
            pass

    assert message["code"] == "busy"
