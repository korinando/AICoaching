"""Read one interview's report in the terminal, while the report page doesn't exist yet.

Run from backend/:
    uv run python -m scripts.show_report 13
"""

import argparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_engine
from app.models import FeedbackReport


def main() -> None:
    parser = argparse.ArgumentParser(description="Read one interview's report.")
    parser.add_argument("session", type=int)
    args = parser.parse_args()

    with Session(get_engine()) as db:
        report = db.scalar(select(FeedbackReport).where(FeedbackReport.session_id == args.session))
        if report is None:
            print(f"Session {args.session} has no report.")
            return
        print(f"Session {args.session}: {report.status}")
        if report.error:
            print(f"Error: {report.error}")
        if report.status != "ready":
            return
        print(f"Overall: {report.overall_score}")
        print(f"Scores: {report.scores}")
        print("Strengths:", *(f"\n  - {s}" for s in report.strengths))
        print("Improvements:", *(f"\n  - {s}" for s in report.improvements))
        for question in report.per_question:
            print(f"\n{question}")


if __name__ == "__main__":
    main()
