"""The Week 3 baseline: how long spoken replies took, from the numbers saved on each turn.

Run from backend/:
    uv run python -m scripts.latency_report
    uv run python -m scripts.latency_report --session 9     # one clean run
"""

import argparse
import math
import statistics

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.interviewer import OWN_WORDS_TEXT, REPEAT_TEXT
from app.core.db import get_engine
from app.models import Turn

# These replies come from a rule with no LLM call, so they'd make the LLM look instant.
RULE_REPLIES = {REPEAT_TEXT, OWN_WORDS_TEXT}
STAGES = [
    ("Whisper (speech to text)", "stt_ms"),
    ("Interviewer (Gemini)", "llm_ms"),
    ("Piper (text to speech)", "tts_ms"),
    ("Server total", "total_latency_ms"),
    ("End of speech to first audio", "first_audio_ms"),
]


def percentile(values: list[int], fraction: float) -> int:
    """The value that this fraction of the measurements are at or below (nearest rank)."""
    ordered = sorted(values)
    return ordered[max(0, math.ceil(fraction * len(ordered)) - 1)]


def summary_line(name: str, values: list[int]) -> str:
    """Median = the typical turn. p90 = a bad turn, which a mean would hide."""
    if not values:
        return f"{name:<30} no measurements"
    median = statistics.median(values)
    p90 = percentile(values, 0.9)
    return f"{name:<30} n={len(values):<4} median {median:>6.0f} ms   p90 {p90:>6} ms"


def main() -> None:
    parser = argparse.ArgumentParser(description="Latency of spoken replies.")
    parser.add_argument("--session", type=int, nargs="+", help="only these sessions (default: all)")
    args = parser.parse_args()

    # stt_ms is only set on replies to a spoken answer.
    query = select(Turn).where(Turn.stt_ms.is_not(None))
    if args.session:
        query = query.where(Turn.session_id.in_(args.session))
    with Session(get_engine()) as db:
        turns = db.scalars(query).all()
    spoken = [t for t in turns if t.text not in RULE_REPLIES]
    print(f"{len(turns)} spoken answers, {len(turns) - len(spoken)} answered by a rule (not shown)")
    for name, column in STAGES:
        values = [v for t in spoken if (v := getattr(t, column)) is not None]
        print(summary_line(name, values))


if __name__ == "__main__":
    main()
