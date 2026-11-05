"""The worker hearing recordings again for scoring. scripts/check_stt.py covers the real models."""

import pytest

from app.models import InterviewSession, Turn
from app.scoring.scorer import build_pairs
from app.services.reports import JOB_TIMEOUT_S
from app.speech.storage import StorageError
from app.speech.stt import SpeechToTextError
from app.workers import jobs
from app.workers.transcripts import with_better_transcripts
from tests.fakes import FakeLLMClient, FakeSpeechToText

BETTER = "what the bigger model heard"
SAVED = "what base.en heard"
RECORDING_KEY = "sessions/1/answer.wav"


@pytest.fixture
def session(db, user, template, storage) -> InterviewSession:
    """One spoken answer, one typed answer, then the closing line."""
    storage.save(RECORDING_KEY, b"the recording", "audio/wav")
    session = InterviewSession(user=user, template=template, agent_state={}, status="completed")
    session.turns = [
        Turn(turn_index=0, speaker="interviewer", text="What is REST?"),
        Turn(turn_index=1, speaker="candidate", text=SAVED, audio_url=RECORDING_KEY),
        Turn(turn_index=2, speaker="interviewer", text="What is an index?"),
        Turn(turn_index=3, speaker="candidate", text="typed answer"),
        Turn(turn_index=4, speaker="interviewer", text="Thank you."),
    ]
    db.add(session)
    db.flush()
    return session


def texts(result) -> list[str]:
    return [t.text for t in result.turns]


def test_spoken_answer_gets_the_better_text(session, storage):
    stt = FakeSpeechToText(BETTER)

    result = with_better_transcripts(session, stt, storage)

    assert texts(result)[1] == BETTER
    assert stt.calls == [b"the recording"]


def test_only_spoken_answers_are_heard_again(session, storage):
    """Questions and typed answers stay exactly as they are, and cost no work."""
    stt = FakeSpeechToText(BETTER)

    result = with_better_transcripts(session, stt, storage)

    assert texts(result) == [
        "What is REST?",
        BETTER,
        "What is an index?",
        "typed answer",
        "Thank you.",
    ]
    assert len(stt.calls) == 1


def test_saved_turns_do_not_change(db, session, storage):
    """The transcript on screen stays what the candidate saw during the interview."""
    with_better_transcripts(session, FakeSpeechToText(BETTER), storage)
    db.flush()
    db.expire_all()

    assert db.get(InterviewSession, session.id).turns[1].text == SAVED


def test_speech_to_text_failure_keeps_the_saved_text(session, storage):
    stt = FakeSpeechToText()
    stt.error = SpeechToTextError("model crashed")

    assert texts(with_better_transcripts(session, stt, storage))[1] == SAVED


def test_storage_failure_keeps_the_saved_text(session, storage):
    storage.error = StorageError("connection refused")

    assert texts(with_better_transcripts(session, FakeSpeechToText(BETTER), storage))[1] == SAVED


def test_hearing_nothing_keeps_the_saved_text(session, storage):
    assert texts(with_better_transcripts(session, FakeSpeechToText(""), storage))[1] == SAVED


def test_the_scorer_can_read_the_result(session, storage):
    pairs = build_pairs(with_better_transcripts(session, FakeSpeechToText(BETTER), storage).turns)

    assert [(p.question, p.answer) for p in pairs] == [
        ("What is REST?", BETTER),
        ("What is an index?", "typed answer"),
    ]


def test_the_job_scores_the_better_text_with_the_right_template(session, storage, monkeypatch):
    seen = {}

    def scorer(scoring_session, llm):
        seen["turns"] = texts(scoring_session)
        seen["role"] = scoring_session.template.role
        seen["llm"] = llm
        return {}

    llm = FakeLLMClient([])
    monkeypatch.setattr(jobs, "score_session", scorer)
    monkeypatch.setattr(jobs, "_llm", lambda: llm)
    monkeypatch.setattr(jobs, "_scoring_speech_to_text", lambda: FakeSpeechToText(BETTER))
    monkeypatch.setattr(jobs, "get_audio_storage", lambda: storage)

    jobs.score_interview(session)

    assert seen["turns"][1] == BETTER
    assert seen["role"] == session.template.role
    assert seen["llm"] is llm


def test_the_job_has_time_for_a_long_interview_and_a_slow_gemini():
    """20 answers at a slow 30 s each, plus Gemini's worst case (220 s). The worker would kill a job
    that passes this limit. The model isn't downloaded here: it's copied in by hand."""
    assert 20 * 30 + 220 < JOB_TIMEOUT_S
