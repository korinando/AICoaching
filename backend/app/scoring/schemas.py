"""The shape of the judge's reply. Field order matters: Gemini writes the fields in this order."""

from pydantic import BaseModel, Field


class ScoreExample(BaseModel):
    """One moment in the conversation that affected a score. The candidate reads only the comment:
    the number and the quote are there so code can check that the moment really happened."""

    question_number: int
    quote: str
    comment: str


class CriterionVerdict(BaseModel):
    """One criterion across the whole interview. In this order on purpose: the judge finds its
    evidence and gives its reasons before committing to a number."""

    examples: list[ScoreExample] = Field(min_length=1, max_length=2)
    explanation: str
    score: int = Field(ge=1, le=5)


class OverallVerdict(BaseModel):
    """One verdict for each of the 4 rubric criteria."""

    technical_accuracy: CriterionVerdict
    clarity: CriterionVerdict
    structure: CriterionVerdict
    depth: CriterionVerdict


class JudgeReply(BaseModel):
    """What Gemini returns. No single overall number: code calculates that from the 4 verdicts."""

    overall: OverallVerdict
    strengths: list[str] = Field(min_length=1, max_length=3)
    improvements: list[str] = Field(min_length=1, max_length=3)
