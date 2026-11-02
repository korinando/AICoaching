"""Word error rate, and that a failing model becomes SpeechToTextError. No real model here."""

import pytest

from app.speech.stt import SpeechToTextError, WhisperSpeechToText
from scripts.check_stt import word_errors


@pytest.mark.parametrize(
    "reference, hypothesis, wrong, words",
    [
        ("add an index", "add an index", 0, 3),
        ("Add an index!", "add an INDEX", 0, 3),  # case and punctuation don't count
        ("add an index", "add a index", 1, 3),  # substituted
        ("add an index", "add index", 1, 3),  # deleted
        ("add an index", "add an extra index", 1, 3),  # inserted
        ("add an index", "", 3, 3),  # heard nothing
    ],
)
def test_word_errors(reference, hypothesis, wrong, words):
    assert word_errors(reference, hypothesis) == (wrong, words)


def test_model_failure_becomes_speech_to_text_error():
    """A model name that doesn't exist fails while loading, which stays inside our error."""
    stt = WhisperSpeechToText("no-such-model")

    with pytest.raises(SpeechToTextError):
        stt.transcribe(b"not used: the model fails to load first")
