"""ffmpeg normalization on its own: no database, no HTTP (Week 3 Step 3)."""

import io
import wave

import pytest

from app.speech.audio import SAMPLE_RATE, AudioError, normalize_audio, wav_duration_seconds


@pytest.mark.parametrize("name", ["webm", "mp4", "ogg"])
def test_every_browser_format_becomes_16khz_mono_wav(audio_samples, name):
    wav = normalize_audio(audio_samples[name])

    with wave.open(io.BytesIO(wav)) as w:
        assert w.getframerate() == SAMPLE_RATE
        assert w.getnchannels() == 1
        assert w.getsampwidth() == 2  # 16-bit samples
    assert wav_duration_seconds(wav) == pytest.approx(2.0, abs=0.1)


def test_not_audio_raises_audio_error():
    """Bytes that only claim to be audio: ffmpeg is the real check."""
    with pytest.raises(AudioError):
        normalize_audio(b"this is a text file pretending to be audio")


def test_short_recording_measures_short(audio_samples):
    assert wav_duration_seconds(normalize_audio(audio_samples["short_webm"])) < 1.0
