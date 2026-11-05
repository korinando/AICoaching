"""Send reports to the worker again: every pending or failed one, or the sessions you name.

Naming a finished session also creates its report, which is how an interview from before reports
existed gets one. A ready report isn't scored again. Run from backend/:
    uv run python -m scripts.retry_reports
    uv run python -m scripts.retry_reports --session 13
    uv run python -m scripts.retry_reports --session 13 --again   # replace a report, even a ready one
"""

import argparse

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.db import get_engine
from app.models import FeedbackReport, InterviewSession
from app.services.reports import queue_report, request_report
from app.workers.queue import get_queue


def main() -> None:
    parser = argparse.ArgumentParser(description="Send reports to the worker again.")
    parser.add_argument("--session", type=int, nargs="+", help="only these sessions")
    parser.add_argument(
        "--again", action="store_true", help="with --session: delete the report and score again"
    )
    args = parser.parse_args()
    if args.again and not args.session:
        parser.error("--again needs --session, so it can't replace every report by accident")

    queue = get_queue()
    with Session(get_engine()) as db:
        if args.session:
            for session_id in args.session:
                session = db.get(InterviewSession, session_id)
                if session is None or session.status == "in_progress":
                    print(f"Session {session_id}: not a finished interview, skipped")
                    continue
                if args.again:
                    db.execute(
                        delete(FeedbackReport).where(FeedbackReport.session_id == session_id)
                    )
                request_report(db, queue, session_id)
                print(f"Session {session_id}: sent")
            return
        waiting = db.scalars(
            select(FeedbackReport.session_id).where(
                FeedbackReport.status.in_(("pending", "failed"))
            )
        ).all()
        for session_id in waiting:
            queue_report(queue, session_id)
        print(f"{len(waiting)} reports sent: {list(waiting)}")


if __name__ == "__main__":
    main()
