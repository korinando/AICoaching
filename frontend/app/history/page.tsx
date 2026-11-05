"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { listSessions, type SessionSummary } from "@/lib/api";
import { useRequireLogin } from "@/lib/useRequireLogin";

export default function HistoryPage() {
  const ready = useRequireLogin();
  const [sessions, setSessions] = useState<SessionSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!ready) return;
    listSessions()
      .then(setSessions)
      .catch((e) =>
        setError(
          e instanceof Error ? e.message : "Could not load your interviews",
        ),
      );
  }, [ready]);

  return (
    <main className="mx-auto w-full max-w-3xl space-y-6 p-4">
      <Link href="/dashboard" className="text-sm text-zinc-500 hover:underline">
        ← Dashboard
      </Link>
      <h1 className="text-2xl font-semibold">Your past interviews</h1>

      {error && <p className="text-sm text-red-600">{error}</p>}
      {!sessions && !error && <p className="text-zinc-500">Loading…</p>}

      {sessions?.length === 0 && (
        <p className="text-zinc-500">
          You haven&apos;t done an interview yet.{" "}
          <Link href="/dashboard" className="underline">
            Start your first one
          </Link>
        </p>
      )}

      {sessions && sessions.length > 0 && (
        <ul className="divide-y divide-zinc-200 rounded-xl border border-zinc-200 dark:divide-zinc-800 dark:border-zinc-800">
          {sessions.map((session) => (
            <li key={session.id}>
              <Row session={session} />
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}

function Row({ session }: { session: SessionSummary }) {
  const inProgress = session.status === "in_progress";
  return (
    <Link
      href={
        inProgress
          ? `/interview/${session.id}`
          : `/interview/${session.id}/report`
      }
      className="flex items-center justify-between gap-4 p-4 hover:bg-zinc-50 dark:hover:bg-zinc-900"
    >
      <div className="min-w-0">
        <p className="truncate font-medium">{session.role}</p>
        <p className="text-sm text-zinc-500">
          {new Date(session.started_at).toLocaleDateString(undefined, {
            year: "numeric",
            month: "short",
            day: "numeric",
          })}
        </p>
      </div>
      <Outcome session={session} />
    </Link>
  );
}

function Outcome({ session }: { session: SessionSummary }) {
  if (session.overall_score !== null) {
    return (
      <p className="shrink-0 text-right">
        <span className="text-xl font-semibold">
          {session.overall_score.toFixed(1)}
        </span>
        <span className="text-sm text-zinc-500"> / 5</span>
      </p>
    );
  }
  const labels: Record<SessionSummary["report_status"], string> = {
    not_finished: "Continue",
    none: "No report yet",
    pending: "Generating…",
    failed: "Report failed",
    ready: "",
  };
  return (
    <p className="shrink-0 text-sm text-zinc-500">
      {labels[session.report_status]}
    </p>
  );
}
