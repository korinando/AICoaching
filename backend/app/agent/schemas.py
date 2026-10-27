from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Action = Literal["follow_up", "next_question", "end"]


class AgentDecision(BaseModel):
    action: Action
    reasoning: str
    text: str


class Message(BaseModel):
    role: Literal["interviewer", "candidate"]
    text: str


class InterviewState(BaseModel):
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
    summary: str = ""
    finished: bool = False

    @property
    def current_topic(self) -> str:
        return self.planned_topics[self.current_topic_index]

    @property
    def last_topic_index(self) -> int:
        return min(len(self.planned_topics), self.max_main_questions) - 1

    @property
    def is_last_topic(self) -> bool:
        return self.current_topic_index >= self.last_topic_index

    @property
    def next_topic(self) -> str | None:
        if self.is_last_topic:
            return None
        return self.planned_topics[self.current_topic_index + 1]

    def allowed_actions(self) -> list[Action]:
        actions: list[Action] = []
        if self.follow_ups_on_current < self.max_follow_ups:
            actions.append("follow_up")
        if self.is_last_topic:
            actions.append("end")
        else:
            actions.append("next_question")
        return actions
