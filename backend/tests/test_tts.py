"""Failures of the real Piper class. No voice file needed. API tests use a fake voice."""

from pathlib import Path

import pytest

from app.speech.tts import PiperTextToSpeech, TextToSpeechError


def test_missing_voice_file_says_how_to_get_it(tmp_path: Path):
    tts = PiperTextToSpeech(tmp_path / "en_US-lessac-medium.onnx")

    with pytest.raises(TextToSpeechError, match="download_voices en_US-lessac-medium"):
        tts.synthesize("Hello")


def test_a_missing_voice_is_downloaded_when_allowed(tmp_path: Path, monkeypatch):
    """In the cloud the voice isn't in the image, so the server fetches it on first load."""
    from app.speech import tts as tts_module

    downloaded = []

    def fake_download(voice: str, download_dir: Path) -> None:
        downloaded.append((voice, download_dir))
        (download_dir / f"{voice}.onnx").write_bytes(b"fake voice")

    monkeypatch.setattr(tts_module, "download_voice", fake_download)
    monkeypatch.setattr(tts_module.PiperVoice, "load", staticmethod(lambda path: "loaded"))
    voice_path = tmp_path / "voices" / "en_US-lessac-medium.onnx"  # the folder doesn't exist yet

    PiperTextToSpeech(voice_path, download_if_missing=True).load()

    assert downloaded == [("en_US-lessac-medium", tmp_path / "voices")]


def test_a_voice_that_exists_is_not_downloaded_again(tmp_path: Path, monkeypatch):
    from app.speech import tts as tts_module

    monkeypatch.setattr(tts_module, "download_voice", lambda *a: pytest.fail("downloaded"))
    monkeypatch.setattr(tts_module.PiperVoice, "load", staticmethod(lambda path: "loaded"))
    voice_path = tmp_path / "en_US-lessac-medium.onnx"
    voice_path.write_bytes(b"fake voice")

    PiperTextToSpeech(voice_path, download_if_missing=True).load()
