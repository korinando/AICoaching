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
    history: list[Message] = []
    summary: str = ""
    finished: bool = False
