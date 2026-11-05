"""Scores a finished interview: Gemini judges the whole of it, code checks and adds up (Week 5)."""

import re
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


def _normalized(text: str) -> str:
    """Only words: a different comma or capital letter isn't a made-up quote."""
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _check_examples(reply: JudgeReply, pairs: list[QuestionAnswer]) -> None:
    """The schema can't see this: every example must really be in the answer it points to. This is
    how an invented moment ("the blank final response") gets caught."""
    answers = {pair.number: _normalized(pair.answer) for pair in pairs}
    for name, verdict in reply.overall:
        for example in verdict.examples:
            answer = answers.get(example.question_number)
            if answer is None:
                raise LLMError(f"{name}: there is no answer {example.question_number}")
            quote = _normalized(example.quote)
            if not quote or quote not in answer:
                raise LLMError(
                    f"{name}: {example.quote!r} isn't in answer {example.question_number}"
                )


def _ask_with_retries(llm: LLMClient, system: str, user: str, pairs: list) -> JudgeReply:
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            reply = llm.complete_json(system, user, JudgeReply)
            _check_examples(reply, pairs)
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

    questions = {pair.number: pair.question for pair in pairs}
    verdicts = reply.overall.model_dump()
    scores = {
        name: {
            "score": verdict["score"],
            "explanation": verdict["explanation"],
            "examples": [
                {
                    "question": questions[example["question_number"]],
                    "quote": example["quote"],
                    "comment": example["comment"],
                }
                for example in verdict["examples"]
            ],
        }
        for name, verdict in verdicts.items()
    }
    return {
        # Code does the adding up, so the number always agrees with the 4 verdicts.
        "overall_score": round(mean(v["score"] for v in verdicts.values()), 2),
        "scores": scores,
        "strengths": reply.strengths,
        "improvements": reply.improvements,
    }
