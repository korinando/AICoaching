"""From an uploaded recording to the text of the answer. Used by both POST /audio and the
WebSocket, so a spoken answer follows the same rules however it arrives."""

import time
from dataclasses import dataclass
from typing import Literal

from app.api.schemas import MAX_ANSWER_CHARS
from app.services.interviews import elapsed_ms
from app.speech.audio import AudioError, normalize_audio, wav_duration_seconds
from app.speech.storage import AudioStorage, StorageError, new_audio_key
from app.speech.stt import SpeechToText, SpeechToTextError

# Opus (Chrome) is about 4 KB per second of speech, so 10 MB is many minutes of talking:
# far more than any answer, but small enough that one request can't fill the server's memory.
MAX_AUDIO_BYTES = 10 * 1024 * 1024
# The plan: reject recordings shorter than about 1 second. The frontend checks this too,
# but the server can't trust the client, so it measures the decoded audio itself.
MIN_AUDIO_SECONDS = 1.0

RejectReason = Literal["too_large", "empty", "unreadable", "too_short", "no_speech", "unavailable"]


class RecordingError(Exception):
    """The recording can't become an answer. Nothing was saved, and the interview is unchanged.

    reason: each endpoint turns it into its own kind of error. message: for the user.
    """

    def __init__(self, reason: RejectReason, message: str) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message


@dataclass
class ProcessedRecording:
    text: str
    audio_key: str
    stt_ms: int


def process_recording(
    data: bytes, session_id: int, speech_to_text: SpeechToText, storage: AudioStorage
) -> ProcessedRecording:
    """Decode -> transcribe -> store. Raises RecordingError."""
    if len(data) > MAX_AUDIO_BYTES:
        raise RecordingError("too_large", "Recording is too long")
    if not data:
        raise RecordingError("empty", "The recording is empty")

    try:
        wav = normalize_audio(data)
    except AudioError:
        # Claimed to be audio, but ffmpeg can't decode it: corrupt, or not audio at all.
        raise RecordingError("unreadable", "Could not read the recording as audio") from None
    if wav_duration_seconds(wav) < MIN_AUDIO_SECONDS:
        raise RecordingError("too_short", "Recording is too short")

    stt_started = time.perf_counter()
    try:
        transcript = speech_to_text.transcribe(wav)
    except SpeechToTextError:
        raise RecordingError("unavailable", "Could not process the recording. Try again.") from None
    stt_ms = elapsed_ms(stt_started)
    if not transcript:
        # Silence or noise: ask again without a turn, an LLM call, or using up the agent's
        # short-answer retries. The candidate hasn't answered anything yet.
        raise RecordingError("no_speech", "No speech detected. Please try again.")

    # Saved after every check, so rejected uploads never take up storage. The WAV rather
    # than the original: bigger, but one format that every browser can play back.
    key = new_audio_key(session_id)
    try:
        storage.save(key, wav, "audio/wav")
    except StorageError:
        raise RecordingError("unavailable", "Could not save the recording. Try again.") from None

    # The same limit as typed answers: 10 MB of audio could transcribe to a very long text.
    return ProcessedRecording(transcript[:MAX_ANSWER_CHARS], key, stt_ms)
