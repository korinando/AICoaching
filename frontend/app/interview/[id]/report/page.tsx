"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import {
  ApiError,
  getReport,
  type Report,
  type ReportCriterion,
  requestReport,
} from "@/lib/api";
import { useRequireLogin } from "@/lib/useRequireLogin";

const POLL_MS = 3000;
const MAX_SCORE = 5;

const CRITERION_LABELS: Record<string, string> = {
  technical_accuracy: "Technical accuracy",
  clarity: "Clarity",
  structure: "Structure",
  depth: "Depth",
};

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

    async function poll() {
      try {
        const latest = await getReport(sessionId);
        if (stopped) return;
        setReport(latest);
        setProblem(null);
        if (latest.status === "pending") timer = setTimeout(poll, POLL_MS);
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
  }, [ready, sessionId, attempt]);

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

  return (
    <main className="mx-auto w-full max-w-2xl flex-1 space-y-6 p-4">
      <header className="flex items-center justify-between gap-4">
        <Link
          href={`/interview/${sessionId}`}
          className="text-sm text-zinc-500 hover:underline"
        >
          ← Interview
        </Link>
        <Link
          href="/dashboard"
          className="text-sm text-zinc-500 hover:underline"
        >
          Dashboard
        </Link>
      </header>
      <h1 className="text-2xl font-semibold">Your feedback report</h1>

      {problem && <p className="text-sm text-red-600">{problem}</p>}

      {report.status === "ready" ? (
        <FinishedReport report={report} />
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

  return (
    <section className="space-y-4 rounded-xl border border-zinc-200 p-6 text-center dark:border-zinc-800">
      <p role="status" className="text-zinc-600 dark:text-zinc-300">
        {messages[report.status]}
      </p>
      {report.can_request && (
        <button
          onClick={onRequest}
          disabled={requesting}
          className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900"
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

function FinishedReport({ report }: { report: Report }) {
  return (
    <>
      <section className="rounded-xl bg-zinc-100 p-6 dark:bg-zinc-800">
        <p className="text-sm text-zinc-500 dark:text-zinc-400">
          Overall score
        </p>
        <p className="text-4xl font-semibold">
          {report.overall_score?.toFixed(1)}
          <span className="text-lg font-normal text-zinc-500 dark:text-zinc-400">
            {" "}
            out of {MAX_SCORE}
          </span>
        </p>
      </section>

      {report.criteria.map((criterion) => (
        <Criterion key={criterion.name} criterion={criterion} />
      ))}

      <FeedbackList title="What went well" items={report.strengths} />
      <FeedbackList title="What to work on" items={report.improvements} />

      <p className="text-xs text-zinc-500">
        Written by AI, so treat it as an opinion and not a final measure. Your
        recordings were listened to again for this report, so its wording can
        differ from the transcript in your interview.
      </p>
    </>
  );
}

function Criterion({ criterion }: { criterion: ReportCriterion }) {
  return (
    <section className="space-y-3 rounded-xl border border-zinc-200 p-5 dark:border-zinc-800">
      <div className="flex items-center justify-between gap-4">
        <h2 className="font-semibold">
          {CRITERION_LABELS[criterion.name] ?? criterion.name}
        </h2>
        <ScoreDots score={criterion.score} />
      </div>
      <p className="text-zinc-700 dark:text-zinc-300">
        {criterion.explanation}
      </p>
      <ul className="space-y-2 border-l-2 border-zinc-200 pl-4 dark:border-zinc-700">
        {criterion.examples.map((example) => (
          <li
            key={example}
            className="text-sm text-zinc-600 dark:text-zinc-400"
          >
            {example}
          </li>
        ))}
      </ul>
    </section>
  );
}

function ScoreDots({ score }: { score: number }) {
  return (
    <div className="flex shrink-0 items-center gap-2">
      <div aria-hidden className="flex gap-1">
        {Array.from({ length: MAX_SCORE }, (_, index) => (
          <span
            key={index}
            className={`h-2.5 w-2.5 rounded-full ${
              index < score
                ? "bg-zinc-900 dark:bg-zinc-100"
                : "bg-zinc-200 dark:bg-zinc-700"
            }`}
          />
        ))}
      </div>
      <span className="text-sm font-medium">
        {score}
        <span className="sr-only"> out of {MAX_SCORE}</span>
      </span>
    </div>
  );
}

function FeedbackList({ title, items }: { title: string; items: string[] }) {
  return (
    <section className="space-y-2">
      <h2 className="font-semibold">{title}</h2>
      <ul className="list-disc space-y-1 pl-5 text-zinc-700 dark:text-zinc-300">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </section>
  );
}

function Note({ children }: { children: React.ReactNode }) {
  return <p className="p-6 text-zinc-500">{children}</p>;
}
