import os

from dotenv import load_dotenv

from app.agent.llm_client import GeminiLLMClient
from app.agent.prompts import build_opening_message, build_system_prompt, build_user_message
from app.agent.schemas import Message
from app.agent.templates import new_state

state = new_state("junior_backend")
print("===== SYSTEM PROMPT (start) =====")
print(build_system_prompt(state))
print("\n===== OPENING MESSAGE =====")
print(build_opening_message(state))

# Pretend we are on the last topic, with 1 follow-up already used
state.current_topic_index = state.last_topic_index
state.follow_ups_on_current = 1
state.history = [
    Message(role="interviewer", text="Tell me about a time you disagreed with a teammate."),
    Message(role="candidate", text="We argued about code style, so we agreed to use a linter."),
]
print("\n===== SYSTEM PROMPT (last topic) =====")
print(build_system_prompt(state))
print("\n===== USER MESSAGE =====")
print(build_user_message(state))

# Send the real prompts to Gemini once
load_dotenv()
llm = GeminiLLMClient(model=os.environ["LLM_MODEL"])
print("\n===== GEMINI DECISION =====")
print(llm.decide(build_system_prompt(state), build_user_message(state)))
