"""Rerun the Step 10 problem situations against the real LLM, several times each.

Instead of a whole interview, each scenario builds the exact state where the problem happened
and sends one answer. The LLM is random, so one good reply proves little: we count passes.

Run from backend/:
    uv run python -m scripts.check_step10            # 3 runs per scenario
    uv run python -m scripts.check_step10 --runs 1
"""

import argparse
import os
from collections.abc import Callable
from dataclasses import dataclass

from dotenv import load_dotenv

from app.agent.interviewer import Interviewer
from app.agent.llm_client import GeminiLLMClient
from app.agent.schemas import InterviewState, Message
from app.agent.templates import new_state


@dataclass
class Scenario:
    name: str
    topic_index: int
    question: str
    answer: str
    # Automatic check on (reply, action). None = read the reply yourself.
    check: Callable[[str, str], bool] | None
    follow_ups_used: int = 0


SCENARIOS = [
    Scenario(
        name="G: vague answer gets a follow-up",
        topic_index=1,
        question="Can you explain the difference between SQL and NoSQL databases?",
        answer="sql using structure schema, while nosql could flexible",
        check=lambda reply, action: action == "follow_up",
    ),
    Scenario(
        name="H: wrong answer, follow-up must not hint 'merge'",
        topic_index=2,
        question="Can you explain the difference between git pull and git fetch?",
        answer="git pull is pulling code from repo, while git fetch is a function of git pull",
        check=lambda reply, action: "merge" not in reply.lower(),
    ),
    Scenario(
        name="B: topic change has a transition",
        topic_index=0,
        question="What is the difference between GET and POST?",
        answer="GET reads data and POST creates data, for example creating a new user.",
        follow_ups_used=2,  # only next_question is allowed, so it must change topic
        check=lambda reply, action: "database" in reply.lower(),
    ),
    Scenario(
        name="E: candidate asks for the answer",
        topic_index=0,
        question="What is the difference between GET and POST?",
        answer="What is the correct answer to your question?",
        check=None,
    ),
    Scenario(
        name="A: no lecturing on 'i work alone'",
        topic_index=4,
        question="How do you handle a disagreement with a teammate?",
        answer="i work alone, i never work with other people",
        check=None,
    ),
]


def build_state(scenario: Scenario) -> InterviewState:
    state = new_state("junior_backend")
    state.current_topic_index = scenario.topic_index
    state.follow_ups_on_current = scenario.follow_ups_used
    state.history = [Message(role="interviewer", text=scenario.question)]
    return state


def action_taken(before: InterviewState, after: InterviewState) -> str:
    """Work out the final action from how the counters moved."""
    if after.finished:
        return "end"
    if after.current_topic_index != before.current_topic_index:
        return "next_question"
    return "follow_up"


def main() -> None:
    parser = argparse.ArgumentParser(description="Rerun Step 10 scenarios against the real LLM.")
    parser.add_argument("--runs", type=int, default=3)
    args = parser.parse_args()

    load_dotenv()
    interviewer = Interviewer(GeminiLLMClient(model=os.environ["LLM_MODEL"]))

    print("F: opening question (read it: basic enough for a junior?)")
    for _ in range(args.runs):
        print(f"   - {interviewer.start(new_state('junior_backend'))}")

    for scenario in SCENARIOS:
        print(f"\n{scenario.name}\n   candidate: {scenario.answer}")
        passed = 0
        for _ in range(args.runs):
            state = build_state(scenario)
            before = state.model_copy(deep=True)
            reply = interviewer.handle_answer(state, scenario.answer)
            action = action_taken(before, state)
            if scenario.check is None:
                mark = "??"
            elif scenario.check(reply, action):
                mark = "ok"
                passed += 1
            else:
                mark = "XX"
            print(f"   {mark} [{action}] {reply}")
        if scenario.check is not None:
            print(f"   => {passed}/{args.runs} passed")


if __name__ == "__main__":
    main()
