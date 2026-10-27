import argparse
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from app.agent.interviewer import Interviewer
from app.agent.llm_client import GeminiLLMClient
from app.agent.schemas import InterviewState
from app.agent.templates import load_templates, new_state

TRANSCRIPTS_DIR = Path(__file__).parent.parent / "transcripts"
QUIT_COMMANDS = {"/quit", "/exit"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a mock interview in the terminal.")
    parser.add_argument(
        "--template",
        default="junior_backend",
        choices=list(load_templates()),
        help="which interview template to use",
    )
    parser.add_argument("--debug", action="store_true", help="show state after each turn")
    return parser.parse_args()


def save_transcript(state: InterviewState) -> Path:
    """Write the full state (including history) to transcripts/<timestamp>.json."""
    TRANSCRIPTS_DIR.mkdir(exist_ok=True)
    filename = datetime.now().strftime("%Y-%m-%d_%H-%M-%S") + ".json"
    path = TRANSCRIPTS_DIR / filename
    path.write_text(state.model_dump_json(indent=2), encoding="utf-8")
    return path


def print_debug(state: InterviewState) -> None:
    """One dim line showing where the interview is, for spotting rule problems."""
    line = (
        f"[state] topic {state.current_topic_index + 1}/{state.last_topic_index + 1} "
        f"({state.current_topic}) | follow-ups {state.follow_ups_on_current}/"
        f"{state.max_follow_ups} | short retries {state.short_answer_retries} | "
        f"finished {state.finished}"
    )
    print(f"\033[2m{line}\033[0m")


def main() -> None:
    args = parse_args()
    load_dotenv()

    state = new_state(args.template)
    interviewer = Interviewer(GeminiLLMClient(model=os.environ["LLM_MODEL"]))

    print(f"=== Mock interview: {state.role} ({state.level}) ===")
    print("Type your answer and press Enter. Type /quit to stop.\n")
    print("Interviewer:", interviewer.start(state))

    try:
        while not state.finished:
            answer = input("\nYou: ").strip()
            if answer.lower() in QUIT_COMMANDS:
                print("\nInterview stopped.")
                break
            print("(thinking...)", end=" ", flush=True)
            reply = interviewer.handle_answer(state, answer)
            print(f"\rInterviewer: {reply}")
            if args.debug:
                print_debug(state)
    except (KeyboardInterrupt, EOFError):
        print("\n\nInterview stopped.")
    finally:
        path = save_transcript(state)
        print(f"\nTranscript saved to {path}")


if __name__ == "__main__":
    main()
