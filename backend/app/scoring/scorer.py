"""Scores a finished interview: Gemini judges each answer, code checks and adds up (Week 5)."""

import time
from dataclasses import dataclass
from statistics import mean
from typing import Any

from app.agent.interviewer import OWN_WORDS_TEXT, REPEAT_TEXT
from app.agent.llm_client import LLMClient, LLMError
from app.models import InterviewSession
from app.scoring.prompts import build_scoring_prompt, build_scoring_system
from app.scoring.schemas import JudgeReply

# Fixed replies from a rule, not real questions: an answer to one still answers the question before.
RULE_REPLIES = {REPEAT_TEXT, OWN_WORDS_TEXT}
# Gemini's 503s pass, so wait between tries. Must fit in the job's 300 s with a 60 s client timeout.
MAX_ATTEMPTS = 3
RETRY_WAIT_S = 20


@dataclass
class QuestionAnswer:
    number: int
    question: str
    answer: str


def build_pairs(turns: list) -> list[QuestionAnswer]:
    pairs = []
    question = None
    for turn in turns:
        if turn.speaker == "interviewer":
            if turn.text not in RULE_REPLIES:
                question = turn.text
        elif question is not None:
            pairs.append(QuestionAnswer(len(pairs) + 1, question, turn.text))
    return pairs


def _check_numbers(reply: JudgeReply, pairs: list[QuestionAnswer]) -> None:
    """The schema can't see this: every answer scored exactly once, and none invented."""
    returned = sorted(q.number for q in reply.per_question)
    expected = [pair.number for pair in pairs]
    if returned != expected:
        raise LLMError(f"Expected questions {expected}, got {returned}")


def _ask_with_retries(llm: LLMClient, system: str, user: str, pairs: list) -> JudgeReply:
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            reply = llm.complete_json(system, user, JudgeReply)
            _check_numbers(reply, pairs)
            return reply
        except LLMError:
            if attempt == MAX_ATTEMPTS:
                raise
            time.sleep(RETRY_WAIT_S)
    raise AssertionError("unreachable")


def score_session(session: InterviewSession, llm: LLMClient) -> dict[str, Any]:
    pairs = build_pairs(session.turns)
    if not pairs:
        raise ValueError("No answers to score")
    system = build_scoring_system(session.template.role, session.template.level)
    reply = _ask_with_retries(llm, system, build_scoring_prompt(pairs), pairs)

    # Code does the adding up, so the numbers always agree with each other.
    all_scores = [q.scores.model_dump() for q in reply.per_question]
    scores = {name: round(mean(s[name] for s in all_scores), 2) for name in all_scores[0]}
    questions = {pair.number: pair for pair in pairs}
    return {
        "overall_score": round(mean(scores.values()), 2),
        "scores": scores,
        "strengths": reply.strengths,
        "improvements": reply.improvements,
        "per_question": [
            {
                "question": questions[q.number].question,
                "answer": questions[q.number].answer,
                **q.model_dump(),
            }
            for q in reply.per_question
        ],
    }
