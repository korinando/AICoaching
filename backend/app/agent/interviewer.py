from app.agent.llm_client import LLMClient, LLMError
from app.agent.prompts import build_opening_message, build_system_prompt, build_user_message
from app.agent.schemas import Action, AgentDecision, InterviewState, Message

# Answers shorter than this get "say a bit more" instead of an LLM call (saves a call, avoids
# judging an empty answer). After MAX_SHORT_ANSWER_RETRIES the short answer is accepted anyway,
# so a candidate who keeps saying "ok" can't loop forever.
MIN_ANSWER_WORDS = 3
MAX_SHORT_ANSWER_RETRIES = 2
REPEAT_TEXT = "Could you say a bit more about that?"
OWN_WORDS_TEXT = "Please answer the question in your own words."
CLOSING_TEXT = "Thank you for your time today. That's the end of our interview."


class Interviewer:
    """Runs an interview: the LLM suggests the next action, code enforces the rules.

    Stateless: all interview data lives in the InterviewState passed to each method,
    so one Interviewer can run many interviews and the state can be saved to a database.
    """

    def __init__(self, llm: LLMClient) -> None:
        # Dependency injection: GeminiLLMClient in real runs, FakeLLMClient in tests.
        self.llm = llm

    def start(self, state: InterviewState) -> str:
        """Greet the candidate and ask the first question. Does not change any counters."""
        try:
            # Only the text is used: nothing has been answered yet, so the action means nothing.
            text = self.llm.decide(build_system_prompt(state), build_opening_message(state)).text
        except LLMError:
            # The interview must never crash because the LLM failed.
            text = (
                f"Hello, thanks for joining. Let's start with {state.current_topic}. "
                "Can you tell me about your experience with it?"
            )
        state.history.append(Message(role="interviewer", text=text))
        return text

    def _decide(self, state: InterviewState) -> AgentDecision:
        """Ask the LLM. On failure retry once with the error, then fall back to a safe decision."""
        system = build_system_prompt(state)
        user = build_user_message(state)
        try:
            return self.llm.decide(system, user)
        except LLMError as first_error:
            print(f"[llm] attempt 1 failed: {first_error}")
            # Telling the model what went wrong often fixes a bad reply; a network error may
            # simply succeed on the second try.
            retry_user = (
                f"{user}\n\nYour previous reply could not be used ({first_error}). "
                "Reply again with valid JSON."
            )
            try:
                return self.llm.decide(system, retry_user)
            except LLMError as second_error:
                print(f"[llm] attempt 2 failed: {second_error}, using fallback")
                return self._fallback_decision(state)

    def _fallback_decision(self, state: InterviewState) -> AgentDecision:
        """A safe decision when the LLM is unavailable: move forward without it."""
        # Always forward, never follow_up: a fallback must not be able to get the interview stuck.
        if state.is_last_topic:
            return AgentDecision(action="end", reasoning="fallback", text=CLOSING_TEXT)
        return AgentDecision(
            action="next_question",
            reasoning="fallback",
            text=f"Let's move on. Can you tell me about your experience with {state.next_topic}?",
        )

    def _enforce_rules(self, state: InterviewState, decision: AgentDecision) -> AgentDecision:
        """If the LLM chose an action that isn't allowed, replace it with the forward action."""
        # Same allowed_actions() the prompt used, so prompt and rules can never disagree.
        if decision.action in state.allowed_actions():
            return decision

        # Every disallowed case means "move forward": follow-ups used up -> next topic,
        # next_question on the last topic -> end, early end -> next topic.
        forward: Action = "end" if state.is_last_topic else "next_question"
        print(f"[rule] {decision.action} not allowed -> {forward}")
        # The LLM's text was written for its own action, so it no longer fits; use our own.
        # Must run before _apply_decision, while state.next_topic still points to the right topic.
        if forward == "end":
            text = CLOSING_TEXT
        else:
            text = f"Thank you. Let's move on to {state.next_topic}. What can you tell me about it?"
        return AgentDecision(
            action=forward, reasoning=f"overridden: {decision.reasoning}", text=text
        )

    def _apply_decision(self, state: InterviewState, action: Action) -> None:
        """Move the counters according to the final action."""
        if action == "follow_up":
            state.follow_ups_on_current += 1
        elif action == "next_question":
            state.current_topic_index += 1
            state.follow_ups_on_current = 0
        else:
            state.finished = True

    def handle_answer(self, state: InterviewState, answer: str) -> str:
        """Process one candidate answer and return what the interviewer says next."""
        if state.finished:
            raise RuntimeError("Interview already finished")

        # Guard clauses: not a real answer -> ask again without calling the LLM.
        # Both share one retry budget, so no mix of pasting and "ok" can loop forever.
        if state.short_answer_retries < MAX_SHORT_ANSWER_RETRIES:
            if _is_pasted_question(state, answer):
                return self._ask_again(state, answer, OWN_WORDS_TEXT)
            if len(answer.split()) < MIN_ANSWER_WORDS:
                return self._ask_again(state, answer, REPEAT_TEXT)

        state.short_answer_retries = 0
        state.history.append(Message(role="candidate", text=answer))

        # The LLM suggests, the rules decide, then the state moves. Order matters:
        # rules must see the state before it changes (see _enforce_rules).
        decision = self._decide(state)
        decision = self._enforce_rules(state, decision)
        self._apply_decision(state, decision.action)
        state.history.append(Message(role="interviewer", text=decision.text))
        return decision.text

    def _ask_again(self, state: InterviewState, answer: str, text: str) -> str:
        """Record the answer and a fixed reply, using one retry. No LLM call, no topic change."""
        state.short_answer_retries += 1
        state.history.append(Message(role="candidate", text=answer))
        state.history.append(Message(role="interviewer", text=text))
        return text


def _is_pasted_question(state: InterviewState, answer: str) -> bool:
    """True if the answer is the last question copied back, with almost nothing added (Step 10)."""
    if not state.history or state.history[-1].role != "interviewer":
        return False  # no question asked yet
    question = state.history[-1].text.strip().lower()
    if not question or question not in answer.lower():
        return False
    # Remove the question and look at what is left: "Interviewer: <question>" leaves 1 word,
    # but "<question> I would ask my teammate..." leaves a real answer, which must go through.
    leftover = answer.lower().replace(question, "")
    return len(leftover.split()) < MIN_ANSWER_WORDS
