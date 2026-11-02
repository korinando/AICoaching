"""Turn any browser recording into one standard format with ffmpeg (Week 3 Step 3).

Chrome sends WebM/Opus, Safari MP4/AAC, Firefox sometimes Ogg. Speech-to-text works best
with one format: 16 kHz, mono, 16-bit PCM WAV, which is what Whisper was trained on.
Decoding with ffmpeg is also the real proof that an upload is audio: the browser's
"audio/..." content type is only a claim.
"""

import io
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

SAMPLE_RATE = 16_000  # samples per second: Whisper's native rate
FFMPEG_TIMEOUT_S = 30  # a few seconds of speech converts in well under 1 s


class AudioError(Exception):
    """The upload isn't audio that ffmpeg can read (corrupt, empty, or not audio at all)."""


def _ffmpeg() -> str:
    """Full path of the ffmpeg program. Missing ffmpeg is a server setup problem, not the
    user's fault, so it's a RuntimeError (500) with a clear message, not an AudioError."""
    path = shutil.which("ffmpeg")
    if path is None:
        raise RuntimeError(
            "ffmpeg is not installed or not on PATH. Windows: winget install --id Gyan.FFmpeg -e"
        )
    return path


def normalize_audio(data: bytes) -> bytes:
    """Any audio format in, 16 kHz mono 16-bit WAV out. Raises AudioError if unreadable."""
    # Real files, not pipes: MP4 (Safari) can keep its index at the end of the file, and
    # ffmpeg can only jump there in a file. A temporary folder is deleted automatically.
    with tempfile.TemporaryDirectory() as folder:
        source = Path(folder) / "input"
        target = Path(folder) / "output.wav"
        source.write_bytes(data)
        command = [
            _ffmpeg(),
            "-hide_banner",
            "-loglevel", "error",  # only real errors in stderr
            "-nostdin",  # never wait for keyboard input
            "-i", str(source),
            "-vn",  # ignore any video track
            "-ac", "1",  # 1 audio channel (mono)
            "-ar", str(SAMPLE_RATE),  # 16 000 samples per second
            "-c:a", "pcm_s16le",  # plain 16-bit samples (what WAV normally holds)
            str(target),
        ]  # fmt: skip
        # A list of arguments, never one string with shell=True: nothing from the upload is
        # ever interpreted as a command (no shell injection).
        try:
            # check=False: a failed conversion is expected (bad uploads) and handled just
            # below with the returncode, instead of as an exception.
            result = subprocess.run(
                command, check=False, capture_output=True, timeout=FFMPEG_TIMEOUT_S
            )
        except subprocess.TimeoutExpired:
            raise AudioError("Converting the recording took too long") from None
        if result.returncode != 0 or not target.exists():
            detail = result.stderr.decode(errors="replace").strip()[-300:]
            raise AudioError(detail or "ffmpeg could not read the recording")
        return target.read_bytes()


def wav_duration_seconds(wav: bytes) -> float:
    """Length of a WAV file: number of samples / samples per second."""
    with wave.open(io.BytesIO(wav)) as w:
        return w.getnframes() / w.getframerate()
