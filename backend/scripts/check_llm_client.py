import os

from dotenv import load_dotenv

from app.agent.llm_client import GeminiLLMClient, LLMError
from app.agent.schemas import AgentDecision
from tests.fakes import FakeLLMClient

SYSTEM = (
    "You are an interviewer for a Junior Backend Developer. Current topic: Databases. "
    "Allowed actions: follow_up, next_question, end. Respond with JSON."
)
USER = (
    "<transcript>\nInterviewer: How would you speed up a slow SQL query?\n"
    "Candidate: I would add an index.\n</transcript>\nDecide the next action."
)

load_dotenv()

# 1. Real client works
real = GeminiLLMClient(model=os.environ["LLM_MODEL"])
print("Real:", real.decide(SYSTEM, USER))

# 2. Real client turns failures into LLMError (this model name does not exist)
broken = GeminiLLMClient(model="gemini-does-not-exist", timeout=20)
try:
    broken.decide(SYSTEM, USER)
except LLMError as e:
    print("Wrapped error:", str(e)[:120])

# 3. Fake client returns scripted answers, in order, and records calls
fake = FakeLLMClient(
    [
        LLMError("simulated outage"),
        AgentDecision(action="next_question", reasoning="scripted", text="Tell me about Git."),
    ]
)
try:
    fake.decide("sys", "first call")
except LLMError as e:
    print("Fake call 1 raised:", e)
print("Fake call 2 returned:", fake.decide("sys", "second call").text)
print("Fake recorded", len(fake.calls), "calls")
