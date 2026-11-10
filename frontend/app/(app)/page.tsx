"use client";

import { ProgressChart } from "@/components/charts";
import { PlusIcon } from "@/components/icons";
import { useOpenNewInterview } from "@/components/NewInterview";
import { useAppData } from "@/lib/appData";

/** The home page: how your scores are going. Interviews are started from the "New interview"
 * pop-up (here or in the sidebar), and past ones are in the sidebar. */
export default function HomePage() {
  const { user, sessions } = useAppData();
  const openNewInterview = useOpenNewInterview();

  const scored = (sessions ?? [])
    .filter((s) => s.overall_score !== null)
    .sort((a, b) => Date.parse(a.started_at) - Date.parse(b.started_at));

  return (
    <main className="mx-auto w-full max-w-4xl space-y-8 px-4 py-8 md:px-8 md:py-12">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="space-y-1">
          <h1 className="text-3xl font-semibold tracking-tight">
            {user ? `Hi ${user.name}` : " "}
          </h1>
          <p className="text-muted">
            Practise out loud, then see how your scores change over time.
          </p>
        </div>
        <button
          type="button"
          onClick={openNewInterview}
          className="flex items-center gap-1.5 rounded-xl bg-accent px-4 py-2.5 text-sm font-medium text-accent-fg hover:bg-accent-hover"
        >
          <PlusIcon className="h-4 w-4" />
          New interview
        </button>
      </header>

      {sessions === null ? (
        <div className="space-y-4" aria-label="Loading">
          <div className="grid grid-cols-3 gap-3">
            {[0, 1, 2].map((i) => (
              <div
                key={i}
                className="h-28 animate-pulse rounded-2xl bg-surface-3"
              />
            ))}
          </div>
          <div className="h-64 animate-pulse rounded-2xl bg-surface-3" />
        </div>
      ) : scored.length === 0 ? (
        <EmptyState started={sessions.length > 0} onStart={openNewInterview} />
      ) : (
        <section aria-labelledby="progress" className="space-y-4">
          <h2 id="progress" className="text-lg font-semibold">
            Your progress
          </h2>
          <Stats scores={scored.map((s) => s.overall_score as number)} />
          <div className="rounded-2xl border border-line bg-surface p-4 md:p-5">
            <h3 className="mb-3 text-sm font-medium text-muted">
              Overall score per interview
            </h3>
            {scored.length >= 2 ? (
              <ProgressChart
                points={scored.map((s) => ({
                  date: s.started_at,
                  score: s.overall_score as number,
                  label: s.role,
                }))}
              />
            ) : (
              <p className="py-6 text-center text-sm text-muted">
                Finish one more interview to see how your score changes.
              </p>
            )}
          </div>
        </section>
      )}
    </main>
  );
}

function EmptyState({
  started,
  onStart,
}: {
  started: boolean;
  onStart: () => void;
}) {
  return (
    <section className="flex flex-col items-center gap-4 rounded-2xl border border-dashed border-line bg-surface px-6 py-14 text-center">
      <h2 className="text-lg font-semibold">
        {started ? "No scores yet" : "Your first interview"}
      </h2>
      <p className="max-w-md text-sm text-muted">
        {started
          ? "Finish an interview with at least 3 answers, and its score shows up here a minute or two later."
          : "Pick a role, answer 5 questions out loud, and get a scored report with what to work on."}
      </p>
      <button
        type="button"
        onClick={onStart}
        className="flex items-center gap-1.5 rounded-xl bg-accent px-4 py-2.5 text-sm font-medium text-accent-fg hover:bg-accent-hover"
      >
        <PlusIcon className="h-4 w-4" />
        Start an interview
      </button>
    </section>
  );
}

function Stats({ scores }: { scores: number[] }) {
  const latest = scores[scores.length - 1];
  const previous = scores.length > 1 ? scores[scores.length - 2] : null;
  const average = scores.reduce((sum, s) => sum + s, 0) / scores.length;
  const change = previous === null ? null : latest - previous;

  return (
    <dl className="grid grid-cols-3 gap-3">
      <Stat label="Latest score" value={latest.toFixed(1)}>
        {change !== null && Math.abs(change) >= 0.05 && (
          <span
            className={`text-xs font-medium ${change > 0 ? "text-success" : "text-danger"}`}
          >
            {change > 0 ? "▲" : "▼"} {Math.abs(change).toFixed(1)} vs previous
          </span>
        )}
      </Stat>
      <Stat label="Average" value={average.toFixed(1)} />
      <Stat label="Scored interviews" value={String(scores.length)} />
    </dl>
  );
}

function Stat({
  label,
  value,
  children,
}: {
  label: string;
  value: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="rounded-2xl border border-line bg-surface p-4">
      <dt className="text-xs text-muted sm:text-sm">{label}</dt>
      <dd className="mt-1 text-2xl font-semibold sm:text-3xl">{value}</dd>
      {children && <dd className="mt-1">{children}</dd>}
    </div>
  );
}
