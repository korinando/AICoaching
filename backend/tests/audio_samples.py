"""Small real audio files for tests, generated with ffmpeg instead of stored in git.

Each one is a plain tone, encoded the way a browser would send it.
"""

import shutil
import subprocess
from pathlib import Path

# name: (file suffix, ffmpeg audio codec, seconds) - like Chrome, Safari, Firefox
SAMPLES = {
    "webm": (".webm", "libopus", 2.0),  # Chrome / Firefox: audio/webm;codecs=opus
    "mp4": (".mp4", "aac", 2.0),  # Safari: audio/mp4
    "ogg": (".ogg", "libopus", 2.0),  # Firefox (sometimes): audio/ogg;codecs=opus
    "short_webm": (".webm", "libopus", 0.4),  # under the 1 s minimum
}


def make_samples(folder: Path) -> dict[str, bytes]:
    """Generate every sample into `folder` and return {name: file bytes}."""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError(
            "ffmpeg is needed for the audio tests: winget install --id Gyan.FFmpeg -e"
        )
    samples = {}
    for name, (suffix, codec, seconds) in SAMPLES.items():
        path = folder / f"{name}{suffix}"
        subprocess.run(
            [
                ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                # lavfi "sine": a built-in generator for a pure tone of the given length
                "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
                "-c:a", codec, str(path),
            ],
            check=True,
        )  # fmt: skip
        samples[name] = path.read_bytes()
    return samples
