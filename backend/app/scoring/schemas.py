from pydantic import BaseModel, Field


class CriterionScores(BaseModel):
    technical_accuracy: int = Field(ge=1, le=5)
    clarity: int = Field(ge=1, le=5)
    structure: int = Field(ge=1, le=5)
    depth: int = Field(ge=1, le=5)


class QuestionFeedback(BaseModel):
    number: int
    scores: CriterionScores
    justification: str
    better_answer_outline: str


class JudgeReply(BaseModel):
    """What Gemini returns. No overall score: code calculates that."""

    per_question: list[QuestionFeedback]
    strengths: list[str] = Field(min_length=1, max_length=3)
    improvements: list[str] = Field(min_length=1, max_length=3)
