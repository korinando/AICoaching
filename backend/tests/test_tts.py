"""Failures of the real Piper class. No voice file needed. API tests use a fake voice."""

from pathlib import Path

import pytest

from app.speech.tts import PiperTextToSpeech, TextToSpeechError


def test_missing_voice_file_says_how_to_get_it(tmp_path: Path):
    tts = PiperTextToSpeech(tmp_path / "en_US-lessac-medium.onnx")

    with pytest.raises(TextToSpeechError, match="download_voices en_US-lessac-medium"):
        tts.synthesize("Hello")
