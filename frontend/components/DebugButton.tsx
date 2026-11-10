"use client";

import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import {
  API_URL,
  getDebugInfo,
  getSessionTimings,
  type DebugInfo,
  type TurnTiming,
} from "@/lib/api";
import { useAppData } from "@/lib/appData";

import { BugIcon, CloseIcon } from "./icons";

/** A small bug icon on the right edge of every signed-in page, for admins only. Hiding it is
 * only for looks: the panel's data comes from /admin endpoints that refuse anyone else.
 * Halfway down the edge, not in a corner: the corners hold the header buttons and the send
 * button on a phone. */
export function DebugButton() {
  const { user } = useAppData();
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [isOpen, setIsOpen] = useState(false);

  if (!user?.is_admin) return null;

  return (
    <>
      <button
        type="button"
        onClick={() => {
          dialogRef.current?.showModal();
          setIsOpen(true);
        }}
        aria-label="Open debug panel"
        title="Debug (admins only)"
        className="fixed right-1 top-1/2 z-20 -translate-y-1/2 p-1.5 text-muted opacity-60 hover:text-foreground hover:opacity-100"
      >
        <BugIcon className="h-5 w-5" />
      </button>
      <dialog
        ref={dialogRef}
        onClose={() => setIsOpen(false)}
        onClick={(e) =>
          e.target === dialogRef.current && dialogRef.current?.close()
        }
        aria-labelledby="debug-title"
        className="ml-auto mr-0 h-dvh max-h-dvh w-[min(26rem,100%)] border-l border-line bg-background p-0 text-foreground shadow-2xl backdrop:bg-black/30"
      >
        {/* Mounted only while open: every opening loads fresh numbers. */}
        {isOpen && <Panel onClose={() => dialogRef.current?.close()} />}
      </dialog>
    </>
  );
}

function Panel({ onClose }: { onClose: () => void }) {
  const { user } = useAppData();
  const pathname = usePathname();
  const sessionId = Number(pathname.match(/^\/interview\/(\d+)/)?.[1]) || null;
  const [info, setInfo] = useState<DebugInfo | null>(null);
  const [timings, setTimings] = useState<TurnTiming[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getDebugInfo()
      .then(setInfo)
      .catch(() => setError("Could not load the server info."));
    if (sessionId) {
      getSessionTimings(sessionId)
        .then(setTimings)
        .catch(() => setError("Could not load this interview's timings."));
    }
  }, [sessionId]);

  return (
    <div className="space-y-6 p-5 text-sm">
      <div className="flex items-center justify-between">
        <h2 id="debug-title" className="text-lg font-semibold">
          Debug
        </h2>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close debug panel"
          className="rounded-md p-1.5 text-muted hover:bg-surface-3"
        >
          <CloseIcon />
        </button>
      </div>

      {error && (
        <p role="alert" className="text-danger">
          {error}
        </p>
      )}

      <Section title="This page">
        <Row label="User id" value={user?.id} />
        <Row label="Interview id" value={sessionId ?? "–"} />
        <Row label="API" value={API_URL} />
      </Section>

      <Section title="Server">
        {info ? (
          <>
            <Row label="Commit" value={info.commit?.slice(0, 7) ?? "local"} />
            <Row
              label="Database"
              value={info.database}
              warn={info.database !== "ok"}
            />
            <Row label="Redis" value={info.redis} warn={info.redis !== "ok"} />
            <Row label="Reports waiting" value={info.queued_reports ?? "–"} />
            <Row label="LLM" value={info.llm_model} />
            <Row label="Speech to text" value={info.whisper_model} />
            <Row label="Scoring STT" value={info.scoring_whisper_model} />
            <Row label="Voice" value={info.piper_voice} />
            <Row label="Interviews per day" value={info.daily_session_limit} />
          </>
        ) : (
          !error && <p className="text-muted">Loading…</p>
        )}
      </Section>

      {sessionId && (
        <Section title="Turn timings (ms)">
          {timings === null ? (
            !error && <p className="text-muted">Loading…</p>
          ) : timings.length === 0 ? (
            <p className="text-muted">No turns yet.</p>
          ) : (
            <TimingTable timings={timings} />
          )}
        </Section>
      )}
    </div>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section>
      <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-muted">
        {title}
      </h3>
      <div className="space-y-1">{children}</div>
    </section>
  );
}

function Row({
  label,
  value,
  warn = false,
}: {
  label: string;
  value: React.ReactNode;
  warn?: boolean;
}) {
  return (
    <div className="flex justify-between gap-4">
      <span className="text-muted">{label}</span>
      <span
        className={`truncate font-mono text-xs leading-5 ${warn ? "text-danger" : ""}`}
      >
        {value}
      </span>
    </div>
  );
}

/** One row per turn. The candidate's turns have the speech-to-text time, the interviewer's the
 * LLM, voice and total; "heard" is end of speech to the reply playing, measured in the browser. */
function TimingTable({ timings }: { timings: TurnTiming[] }) {
  const cell = (ms: number | null) => (ms === null ? "–" : ms);
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-right font-mono text-xs tabular-nums">
        <thead className="text-muted">
          <tr>
            <th className="py-1 text-left font-medium">#</th>
            <th className="font-medium">STT</th>
            <th className="font-medium">LLM</th>
            <th className="font-medium">TTS</th>
            <th className="font-medium">Total</th>
            <th className="font-medium">Heard</th>
          </tr>
        </thead>
        <tbody>
          {timings.map((t) => (
            <tr key={t.turn_index} className="border-t border-line">
              <td className="py-1 text-left">
                {t.turn_index} {t.speaker === "candidate" ? "you" : "AI"}
              </td>
              <td>{cell(t.stt_ms)}</td>
              <td>{cell(t.llm_ms)}</td>
              <td>{cell(t.tts_ms)}</td>
              <td>{cell(t.total_latency_ms)}</td>
              <td>{cell(t.first_audio_ms)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
