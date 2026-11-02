"""Measure the real Whisper model: transcripts, speed and word error rate (WER).

No API call: everything runs on this PC. The first run downloads the model.

Run from backend/:
    uv run python -m scripts.check_stt some_recording.wav
    uv run python -m scripts.check_stt --storage sessions/5/abc.wav     # from the bucket
    uv run python -m scripts.check_stt --folder my_answers --model small.en

--folder holds pairs: answer1.wav + answer1.txt (what was really said), so WER can be
measured. Keep it outside git: these are recordings of your voice.
"""

import argparse
import re
import time
from pathlib import Path

from app.api.deps import get_audio_storage
from app.core.config import get_settings
from app.speech.audio import normalize_audio, wav_duration_seconds
from app.speech.stt import WhisperSpeechToText


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


def word_errors(reference: str, hypothesis: str) -> tuple[int, int]:
    """(wrong words, words in the reference). WER = wrong / reference.

    "Wrong" is the edit distance between the word lists: the fewest words to substitute,
    insert or delete to turn what Whisper heard into what was really said.
    """
    ref, hyp = _words(reference), _words(hypothesis)
    # previous[j]: distance between the words of ref handled so far and the first j of hyp.
    previous = list(range(len(hyp) + 1))
    for i, ref_word in enumerate(ref, start=1):
        current = [i]
        for j, hyp_word in enumerate(hyp, start=1):
            substitute = previous[j - 1] + (ref_word != hyp_word)
            current.append(min(substitute, previous[j] + 1, current[j - 1] + 1))
        previous = current
    return previous[-1], len(ref)


def measure(stt: WhisperSpeechToText, data: bytes) -> tuple[str, float, float]:
    """(transcript, seconds of audio, seconds to transcribe)."""
    wav = normalize_audio(data)
    started = time.perf_counter()
    transcript = stt.transcribe(wav)
    return transcript, wav_duration_seconds(wav), time.perf_counter() - started


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure speech-to-text on real audio.")
    parser.add_argument("file", nargs="?", help="an audio file on disk")
    parser.add_argument("--storage", help="key of a stored recording")
    parser.add_argument("--folder", help="folder of audio + .txt pairs, to measure WER")
    parser.add_argument("--model", default=get_settings().whisper_model)
    args = parser.parse_args()

    stt = WhisperSpeechToText(args.model)
    print(f"Model: {args.model}")

    if args.folder:
        wrong = total = 0
        for text_file in sorted(Path(args.folder).glob("*.txt")):
            audio_file = next(
                p for p in text_file.parent.glob(f"{text_file.stem}.*") if p.suffix != ".txt"
            )
            transcript, audio_s, took_s = measure(stt, audio_file.read_bytes())
            errors, words = word_errors(text_file.read_text(encoding="utf-8"), transcript)
            wrong, total = wrong + errors, total + words
            print(f"{audio_file.name}: {errors}/{words} wrong, {audio_s:.1f} s in {took_s:.1f} s")
            print(f"   heard: {transcript}")
        print(f"WER: {wrong}/{total} = {wrong / total:.1%}")
        return

    if args.storage:
        storage = get_audio_storage()
        data = storage.client.get_object(Bucket=storage.bucket, Key=args.storage)["Body"].read()
    else:
        data = Path(args.file).read_bytes()
    transcript, audio_s, took_s = measure(stt, data)
    print(f"{audio_s:.1f} s of audio, transcribed in {took_s:.1f} s")
    print(f"Heard: {transcript!r}")


if __name__ == "__main__":
    main()
