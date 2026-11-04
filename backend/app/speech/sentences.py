"""Cutting streamed text into sentences, so each can be spoken as soon as it's complete."""

import re
from collections.abc import Iterable, Iterator

# Too short to speak alone: "Thanks." sounds better joined to what follows.
MIN_SENTENCE_CHARS = 15
ABBREVIATIONS = ("e.g.", "i.e.", "vs.")
SENTENCE_END = re.compile(r"[.?!]+\s+")


def _find_cut(buffer: str) -> int | None:
    """Where the first complete sentence ends, or None if there isn't one yet."""
    for match in SENTENCE_END.finditer(buffer):
        sentence = buffer[: match.end()].strip()
        if len(sentence) >= MIN_SENTENCE_CHARS and not sentence.lower().endswith(ABBREVIATIONS):
            return match.end()
    return None


def split_sentences(pieces: Iterable[str]) -> Iterator[str]:
    """Yield each sentence as soon as it's complete, then whatever is left at the end."""
    buffer = ""
    for piece in pieces:
        buffer += piece
        while (cut := _find_cut(buffer)) is not None:
            yield buffer[:cut].strip()
            buffer = buffer[cut:]
    if buffer.strip():
        yield buffer.strip()
