"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { ScoreBars } from "@/components/charts";
import { CheckIcon, SendIcon } from "@/components/icons";
import {
  ApiError,
  getReport,
  type Report,
  type ReportCriterion,
  requestReport,
} from "@/lib/api";
import { useAppData } from "@/lib/appData";
import { useRequireLogin } from "@/lib/useRequireLogin";

const POLL_MS = 3000;
const MAX_SCORE = 5;

const CRITERION_LABELS: Record<string, string> = {
  technical_accuracy: "Technical accuracy",
  clarity: "Clarity",
  structure: "Structure",
  depth: "Depth",
};

const label = (name: string) => CRITERION_LABELS[name] ?? name;

/** Suspense for the same reason as the interview page: the [id] is only known in the browser. */
export default function ReportPage() {
  return (
    <Suspense fallback={<Note>Loading…</Note>}>
      <ReportView />
    </Suspense>
  );
}

function ReportView() {
  const ready = useRequireLogin();
  const { id } = useParams<{ id: string }>();
  const sessionId = Number(id);
  const { sessions, refreshSessions } = useAppData();

  const [report, setReport] = useState<Report | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [requesting, setRequesting] = useState(false);
  const [attempt, setAttempt] = useState(0); // goes up to start polling again after a request

  // Asks again every few seconds until the report has left "pending". Each poll waits for the one
  // before it, so a slow server can't pile up requests.
  useEffect(() => {
    if (!ready) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let wasPending = false;

    async function poll() {
      try {
        const latest = await getReport(sessionId);
        if (stopped) return;
        setReport(latest);
        setProblem(null);
        if (latest.status === "pending") {
          wasPending = true;
          timer = setTimeout(poll, POLL_MS);
        } else if (wasPending) {
          void refreshSessions(); // the score appears in the sidebar too
        }
      } catch (e) {
        if (stopped) return;
        if (e instanceof ApiError && e.status === 404) {
          setNotFound(true);
          return;
        }
        // Keep what's on screen and keep trying: this is usually a short break in the connection.
        setProblem("Can't reach the server. Trying again…");
        timer = setTimeout(poll, POLL_MS);
      }
    }

    void poll();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [ready, sessionId, attempt, refreshSessions]);

  async function askForReport() {
    setRequesting(true);
    setProblem(null);
    try {
      setReport(await requestReport(sessionId));
      setAttempt((current) => current + 1);
    } catch (e) {
      setProblem(
        e instanceof Error ? e.message : "Could not ask for the report.",
      );
    } finally {
      setRequesting(false);
    }
  }

  if (notFound) return <Note>Interview not found.</Note>;
  if (!report) return <Note>{problem ?? "Loading…"}</Note>;

  const summary = sessions?.find((s) => s.id === sessionId);
  // The score of the interview before this one, for "+0.4 since last time".
  const previous = sessions
    ?.filter(
      (s) =>
        s.overall_score !== null &&
        summary &&
        Date.parse(s.started_at) < Date.parse(summary.started_at),
    )
    .sort((a, b) => Date.parse(b.started_at) - Date.parse(a.started_at))[0];

  return (
    <main className="mx-auto w-full max-w-3xl space-y-8 px-4 py-8 md:px-8 md:py-10">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-sm text-muted">{summary?.role ?? "Interview"}</p>
          <h1 className="text-3xl font-semibold tracking-tight">
            Feedback report
          </h1>
        </div>
        <Link
          href={`/interview/${sessionId}`}
          className="rounded-lg border border-line px-3 py-1.5 text-sm hover:bg-surface-3"
        >
          Read the transcript
        </Link>
      </header>

      {problem && (
        <p role="alert" className="text-sm text-danger">
          {problem}
        </p>
      )}

      {report.status === "ready" ? (
        <FinishedReport
          report={report}
          previousScore={previous?.overall_score ?? null}
        />
      ) : (
        <Waiting
          report={report}
          requesting={requesting}
          onRequest={askForReport}
        />
      )}
    </main>
  );
}

function Waiting({
  report,
  requesting,
  onRequest,
}: {
  report: Report;
  requesting: boolean;
  onRequest: () => void;
}) {
  const messages: Record<Report["status"], string> = {
    not_finished: "Your report will be ready after the interview ends.",
    none: "This interview doesn't have a report yet.",
    pending: report.can_request
      ? "This is taking longer than it should."
      : "Generating your report… This can take a few minutes, because your recordings are listened to again.",
    failed:
      "We couldn't finish your report. Your interview is saved, so you can try again.",
    too_short:
      "This interview was too short to score: a report needs at least 3 real answers. Your answers are still saved.",
    ready: "",
  };
  const working = report.status === "pending" && !report.can_request;

  return (
    <section className="flex flex-col items-center gap-4 rounded-2xl border border-line bg-surface p-8 text-center">
      {working && (
        <span
          aria-hidden
          className="h-8 w-8 animate-spin rounded-full border-2 border-line border-t-accent motion-reduce:animate-none"
        />
      )}
      <p role="status" className="max-w-md text-muted">
        {messages[report.status]}
      </p>
      {report.can_request && (
        <button
          onClick={onRequest}
          disabled={requesting}
          className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-accent-fg hover:bg-accent-hover disabled:opacity-50"
        >
          {requesting
            ? "Asking…"
            : report.status === "none"
              ? "Create report"
              : "Try again"}
        </button>
      )}
    </section>
  );
}

function FinishedReport({
  report,
  previousScore,
}: {
  report: Report;
  previousScore: number | null;
}) {
  const overall = report.overall_score ?? 0;
  const change = previousScore === null ? null : overall - previousScore;

  return (
    <>
      <section className="grid gap-6 rounded-2xl border border-line bg-surface p-6 md:grid-cols-[auto_1fr] md:gap-10">
        <div className="flex flex-col justify-center">
          <p className="text-sm text-muted">Overall score</p>
          <p className="text-6xl font-semibold tracking-tight">
            {overall.toFixed(1)}
            <span className="text-xl font-normal text-muted">
              {" "}
              / {MAX_SCORE}
            </span>
          </p>
          {change !== null && Math.abs(change) >= 0.05 && (
            <p
              className={`mt-1 text-sm font-medium ${change > 0 ? "text-success" : "text-danger"}`}
            >
              {change > 0 ? "▲" : "▼"} {Math.abs(change).toFixed(1)} since your
              last interview
            </p>
          )}
          <p className="mt-2 max-w-48 text-xs text-muted">
            The average of the 4 criteria
          </p>
        </div>
        <div>
          <h2 className="mb-2 text-sm font-medium text-muted">
            Score per criterion
          </h2>
          <ScoreBars
            bars={report.criteria.map((c) => ({
              label: label(c.name),
              score: c.score,
            }))}
          />
        </div>
      </section>

      <div className="grid gap-4 md:grid-cols-2">
        <FeedbackList
          title="What went well"
          items={report.strengths}
          icon={<CheckIcon className="h-4 w-4 text-success" />}
        />
        <FeedbackList
          title="What to work on"
          items={report.improvements}
          icon={<SendIcon className="h-4 w-4 rotate-45 text-accent" />}
        />
      </div>

      <section className="space-y-4">
        <h2 className="text-lg font-semibold">In detail</h2>
        {report.criteria.map((criterion) => (
          <Criterion key={criterion.name} criterion={criterion} />
        ))}
      </section>

      <p className="text-xs text-muted">
        Written by AI, so treat it as an opinion and not a final measure. Your
        recordings were listened to again for this report, so its wording can
        differ from the transcript in your interview.
      </p>
    </>
  );
}

function Criterion({ criterion }: { criterion: ReportCriterion }) {
  return (
    <article className="space-y-3 rounded-2xl border border-line bg-surface p-5">
      <div className="flex items-center justify-between gap-4">
        <h3 className="font-semibold">{label(criterion.name)}</h3>
        <span className="rounded-lg bg-accent-soft px-2 py-0.5 text-sm font-semibold tabular-nums text-accent">
          {criterion.score}
          <span className="font-normal"> / {MAX_SCORE}</span>
        </span>
      </div>
      <p className="leading-relaxed">{criterion.explanation}</p>
      <ul className="space-y-2">
        {criterion.examples.map((example) => (
          <li
            key={example}
            className="border-l-2 border-accent/40 pl-3 text-sm text-muted"
          >
            {example}
          </li>
        ))}
      </ul>
    </article>
  );
}

function FeedbackList({
  title,
  items,
  icon,
}: {
  title: string;
  items: string[];
  icon: React.ReactNode;
}) {
  return (
    <section className="space-y-3 rounded-2xl border border-line bg-surface p-5">
      <h2 className="font-semibold">{title}</h2>
      <ul className="space-y-2.5">
        {items.map((item) => (
          <li key={item} className="flex gap-2.5 text-sm leading-relaxed">
            <span className="mt-0.5 shrink-0">{icon}</span>
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Note({ children }: { children: React.ReactNode }) {
  return <p className="p-6 text-muted">{children}</p>;
}
