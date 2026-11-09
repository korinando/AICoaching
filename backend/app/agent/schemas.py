"""The agent's data: its decisions, the conversation, and the interview state."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Action = Literal["follow_up", "next_question", "end"]


class AgentDecision(BaseModel):
    """What the interviewer does next and what it says. reasoning is for debugging only."""

    action: Action
    reasoning: str
    text: str


class Message(BaseModel):
    """One thing said in the interview, by either side."""

    role: Literal["interviewer", "candidate"]
    text: str


class InterviewState(BaseModel):
    """Everything needed to continue an interview, saved after every turn.

    The counters are what the rules are checked against: which topic is current, how many
    follow-ups it has had, and how many short answers were asked again. validate_assignment
    re-checks every change, so a counter can never go below 0.
    """

    model_config = ConfigDict(validate_assignment=True)
    role: str
    level: str
    interview_type: str
    planned_topics: list[str]
    current_topic_index: int = Field(default=0, ge=0)
    follow_ups_on_current: int = Field(default=0, ge=0)
    max_follow_ups: int = 2
    max_main_questions: int = 6
    short_answer_retries: int = Field(default=0, ge=0)
    history: list[Message] = []
    finished: bool = False

    @property
    def current_topic(self) -> str:
        """The topic being asked about now."""
        return self.planned_topics[self.current_topic_index]

    @property
    def last_topic_index(self) -> int:
        """The index of the last topic: max_main_questions can cut the plan short."""
        return min(len(self.planned_topics), self.max_main_questions) - 1

    @property
    def is_last_topic(self) -> bool:
        """True on the final topic, the only one where the interview can end."""
        return self.current_topic_index >= self.last_topic_index

    @property
    def next_topic(self) -> str | None:
        """The topic after this one, or None on the last topic."""
        if self.is_last_topic:
            return None
        return self.planned_topics[self.current_topic_index + 1]

    def allowed_actions(self) -> list[Action]:
        """The actions the rules allow right now. The prompt offers only these, and the code
        replaces any other choice, so the prompt and the rules can never disagree:
        - follow_up while this topic has had fewer than max_follow_ups;
        - next_question on any topic but the last, and end only on the last.
        """
        actions: list[Action] = []
        if self.follow_ups_on_current < self.max_follow_ups:
            actions.append("follow_up")
        if self.is_last_topic:
            actions.append("end")
        else:
            actions.append("next_question")
        return actions
