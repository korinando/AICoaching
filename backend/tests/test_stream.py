"""The streaming interviewer (Week 4 Step 3): a text format instead of JSON, so the action is
known before the first word, and the rules can run before anything is spoken."""

from types import SimpleNamespace

import pytest

from app.agent.interviewer import CLOSING_TEXT, OWN_WORDS_TEXT, REPEAT_TEXT, Interviewer
from app.agent.llm_client import GeminiLLMClient, LLMError, TokenUsage, read_action
from app.agent.prompts import build_system_prompt
from app.agent.schemas import Message
from tests.fakes import ANSWER, FakeLLMClient

# --- read_action -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("chunks", "action", "text"),
    [
        (["ACTION: follow_up\nHi there"], "follow_up", "Hi there"),
        (["ACTION", ": end\n", "Thanks"], "end", "Thanks"),  # split inside the action line
        (["ACTION: end\n", "Thanks"], "end", "Thanks"),  # split right after the newline
        (["ACTION: end\n\n", "Thanks"], "end", "Thanks"),  # a blank line before the text
        (["  ACTION : end  \nThanks"], "end", "Thanks"),  # extra spaces around the action
        (["ACTION: follow_up\nWhat: why?"], "follow_up", "What: why?"),  # a colon in the text
        (["ACTION: end\nOne.\nTwo."], "end", "One.\nTwo."),  # only the first line is special
        (["ACTION", ": follow_up\nCan you", " explain", "?"], "follow_up", "Can you explain?"),
    ],
)
def test_read_action_finds_the_action_and_the_text(chunks, action, text):
    found, pieces = read_action(chunks)

    assert found == action
    assert "".join(pieces) == text


@pytest.mark.parametrize(
    "chunks",
    [
        [],
        [""],
        ["ACTION: banana\nHi"],  # not an action
        ["Sure! Here is my answer\nmore"],  # no action line
        ["ACTION: end"],  # no newline, ever
        ["ACTION: end\n"],  # an action, but nothing to say
        ["ACTION: end\n  \n"],  # only spaces to say
    ],
)
def test_read_action_rejects_replies_with_no_action_or_nothing_to_say(chunks):
    with pytest.raises(LLMError):
        read_action(chunks)


def test_read_action_stops_reading_once_it_has_the_first_words():
    def chunks():
        yield "ACTION: follow_up\nHi"
        raise AssertionError("read too far: this would not be streaming")

    action, pieces = read_action(chunks())

    assert action == "follow_up"
    assert next(pieces) == "Hi"


def test_read_action_loses_no_piece_and_repeats_none():
    """The iterator must continue where read_action stopped, also when given a generator."""
    _action, pieces = read_action(iter(["ACTION: end\nA", "B", "C"]))

    assert list(pieces) == ["A", "B", "C"]


# --- stream_answer: the normal path ------------------------------------------------------------


def test_reply_arrives_piece_by_piece_without_the_action_line(state):
    llm = FakeLLMClient([["ACTION: follow_up\nWhy", " is", " that?"]])

    pieces = list(Interviewer(llm).stream_answer(state, ANSWER))

    assert pieces == ["Why", " is", " that?"]
    assert state.follow_ups_on_current == 1
    assert [(m.role, m.text) for m in state.history] == [
        ("candidate", ANSWER),
        ("interviewer", "Why is that?"),
    ]


def test_state_only_moves_after_the_last_piece(state):
    """A reader that stops halfway must not use up a follow-up for a question never finished."""
    llm = FakeLLMClient([["ACTION: follow_up\nA", "B"]])
    reply = Interviewer(llm).stream_answer(state, ANSWER)

    assert next(reply) == "A"
    assert state.follow_ups_on_current == 0

    list(reply)
    assert state.follow_ups_on_current == 1


def test_nothing_runs_until_someone_reads_the_reply(state):
    llm = FakeLLMClient([])

    Interviewer(llm).stream_answer(state, ANSWER)  # never read

    assert llm.calls == []
    assert state.history == []


def test_next_question_moves_to_the_next_topic(state):
    llm = FakeLLMClient([["ACTION: next_question\nLet's move on to Databases."]])

    list(Interviewer(llm).stream_answer(state, ANSWER))

    assert state.current_topic_index == 1
    assert state.follow_ups_on_current == 0


def test_end_on_the_last_topic_finishes(state):
    state.current_topic_index = state.last_topic_index
    llm = FakeLLMClient([["ACTION: end\nThank you."]])

    assert "".join(Interviewer(llm).stream_answer(state, ANSWER)) == "Thank you."
    assert state.finished


def test_asks_with_the_streaming_format(state):
    llm = FakeLLMClient([["ACTION: follow_up\nWhy?"]])

    list(Interviewer(llm).stream_answer(state, ANSWER))

    system, user = llm.calls[0]
    assert "ACTION: <one allowed action>" in system
    assert "JSON" not in system
    assert ANSWER in user


def test_json_prompt_is_unchanged_for_the_http_routes(state):
    system = build_system_prompt(state)

    assert "Respond with JSON" in system
    assert "ACTION:" not in system


# --- stream_answer: the rules ------------------------------------------------------------------


def test_rule_override_means_the_llms_text_is_never_spoken(state):
    state.follow_ups_on_current = state.max_follow_ups
    llm = FakeLLMClient([["ACTION: follow_up\nSECRET"]])

    spoken = "".join(Interviewer(llm).stream_answer(state, ANSWER))

    assert "SECRET" not in spoken
    assert state.current_topic_index == 1
    assert state.history[-1].text == spoken


def test_early_end_is_overridden_to_the_next_topic(state):
    llm = FakeLLMClient([["ACTION: end\nSECRET"]])

    spoken = "".join(Interviewer(llm).stream_answer(state, ANSWER))

    assert "SECRET" not in spoken
    assert not state.finished
    assert state.current_topic_index == 1


def test_next_question_on_the_last_topic_is_overridden_to_the_end(state):
    state.current_topic_index = state.last_topic_index
    llm = FakeLLMClient([["ACTION: next_question\nSECRET"]])

    assert "".join(Interviewer(llm).stream_answer(state, ANSWER)) == CLOSING_TEXT
    assert state.finished


# --- stream_answer: short and pasted answers -----------------------------------------------------


def test_short_answer_gets_the_fixed_reply_without_the_llm(state):
    llm = FakeLLMClient([])

    assert list(Interviewer(llm).stream_answer(state, "yes")) == [REPEAT_TEXT]
    assert llm.calls == []
    assert state.short_answer_retries == 1


def test_pasted_question_gets_the_fixed_reply_without_the_llm(state):
    question = "What is an index?"
    llm = FakeLLMClient([])
    interviewer = Interviewer(llm)
    state.history.append(Message(role="interviewer", text=question))

    assert list(interviewer.stream_answer(state, question)) == [OWN_WORDS_TEXT]
    assert llm.calls == []


def test_short_answers_stop_being_rejected_after_the_retry_budget(state):
    llm = FakeLLMClient([["ACTION: follow_up\nWhy?"]])
    interviewer = Interviewer(llm)

    list(interviewer.stream_answer(state, "yes"))
    list(interviewer.stream_answer(state, "yes"))
    assert list(interviewer.stream_answer(state, "yes")) == ["Why?"]

    assert state.short_answer_retries == 0


def test_finished_interview_refuses_answers(state):
    state.finished = True

    with pytest.raises(RuntimeError):
        list(Interviewer(FakeLLMClient([])).stream_answer(state, ANSWER))


# --- stream_answer: failures -------------------------------------------------------------------


@pytest.mark.parametrize(
    "first_failure",
    [LLMError("network"), ["garbage\nmore"], ["ACTION: follow_up\n"]],
    ids=["network", "no_action", "nothing_to_say"],
)
def test_bad_first_reply_is_retried_with_the_reason(state, first_failure):
    llm = FakeLLMClient([first_failure, ["ACTION: follow_up\nWhy?"]])

    assert "".join(Interviewer(llm).stream_answer(state, ANSWER)) == "Why?"
    assert len(llm.calls) == 2
    assert "could not be used" in llm.calls[1][1]
    assert state.follow_ups_on_current == 1


def test_two_failures_fall_back_to_the_next_topic(state):
    llm = FakeLLMClient([LLMError("first"), LLMError("second")])

    spoken = "".join(Interviewer(llm).stream_answer(state, ANSWER))

    assert "Databases" in spoken
    assert state.current_topic_index == 1
    assert state.history[-1].text == spoken


def test_two_failures_on_the_last_topic_end_the_interview(state):
    state.current_topic_index = state.last_topic_index
    llm = FakeLLMClient([LLMError("first"), LLMError("second")])

    assert "".join(Interviewer(llm).stream_answer(state, ANSWER)) == CLOSING_TEXT
    assert state.finished


def test_failure_after_speaking_keeps_what_was_said_and_does_not_retry(state):
    """Words already spoken can't be taken back. History must match what was heard."""

    class CutOff(FakeLLMClient):
        def stream(self, system, user):
            self.calls.append((system, user))
            yield "ACTION: follow_up\nCan you"
            raise LLMError("connection lost")

    llm = CutOff([])

    spoken = "".join(Interviewer(llm).stream_answer(state, ANSWER))

    assert spoken == "Can you"
    assert len(llm.calls) == 1
    assert state.history[-1].text == "Can you"
    assert state.follow_ups_on_current == 1


# --- GeminiLLMClient.stream: the SDK replaced by a stand-in ------------------------------------


def chunk(text, usage=None):
    return SimpleNamespace(text=text, usage_metadata=usage)


def sdk_usage():
    return SimpleNamespace(
        prompt_token_count=100,
        candidates_token_count=20,
        thoughts_token_count=50,
        total_token_count=170,
    )


def client_returning(*chunks, error=None, timeout=60):
    """A real GeminiLLMClient whose SDK call is replaced, so no test reaches the network."""
    seen = {}

    def generate_content_stream(model, contents, config):
        seen.update(model=model, contents=contents, config=config)
        yield from chunks
        if error:
            raise error

    client = GeminiLLMClient(model="test-model", api_key="not-a-real-key", timeout=timeout)
    client.client = SimpleNamespace(
        models=SimpleNamespace(generate_content_stream=generate_content_stream)
    )
    return client, seen


def test_stream_yields_text_and_skips_empty_chunks():
    client, _seen = client_returning(chunk("Hello"), chunk(""), chunk(None), chunk(" there"))

    assert list(client.stream("system", "user")) == ["Hello", " there"]


def test_stream_sends_the_prompts_and_a_timeout_in_milliseconds():
    client, seen = client_returning(chunk("Hello"), timeout=60)

    list(client.stream("system", "user"))

    assert seen["model"] == "test-model"
    assert seen["contents"] == "user"
    assert seen["config"].system_instruction == "system"
    assert seen["config"].http_options.timeout == 60_000


def test_stream_turns_any_failure_into_llm_error():
    client, _seen = client_returning(chunk("Hello"), error=ConnectionError("lost"))
    reply = client.stream("system", "user")

    assert next(reply) == "Hello"
    with pytest.raises(LLMError, match="ConnectionError"):
        next(reply)


def test_stream_counts_tokens_from_the_chunk_that_has_them():
    client, _seen = client_returning(chunk("Hello", sdk_usage()), chunk(""))

    list(client.stream("system", "user"))

    assert client.usage.calls == 1
    assert client.usage.input_tokens == 100
    assert client.usage.output_tokens == 20
    assert client.usage.thought_tokens == 50
    assert client.usage.total_tokens == 170


@pytest.mark.parametrize(
    "error", [ConnectionError("lost"), None], ids=["failed", "reader_stopped_early"]
)
def test_stream_counts_the_call_even_if_it_never_finishes(error):
    client, _seen = client_returning(chunk("Hello", sdk_usage()), chunk("more"), error=error)
    reply = client.stream("system", "user")

    next(reply)
    reply.close()

    assert client.usage.calls == 1
    assert client.usage.total_tokens == 170


def test_add_stream_handles_missing_usage():
    """The SDK types these as Optional: None must not crash or add anything."""
    usage = TokenUsage()

    usage.add_stream(None)

    assert usage.calls == 1
    assert usage.total_tokens == 0
