"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import {
  type KeyboardEvent,
  Suspense,
  useEffect,
  useRef,
  useState,
} from "react";

import { TalkButton } from "@/components/TalkButton";
import {
  ApiError,
  getSession,
  sendAnswer,
  type Session,
  type Turn,
  uploadAudio,
} from "@/lib/api";
import type { Recording } from "@/lib/useRecorder";
import { useRequireLogin } from "@/lib/useRequireLogin";

/** The [id] in the URL is only known when someone opens the page, not at build time.
 * next.config has cacheComponents on, so Next.js prerenders pages during the build; reading
 * the URL must happen inside <Suspense>, which shows the fallback until the value exists. */
export default function InterviewPage() {
  return (
    <Suspense fallback={<Message text="Loading…" />}>
      <Interview />
    </Suspense>
  );
}

function Interview() {
  const ready = useRequireLogin();
  // Next.js 16: a client component reads the [id] part of the URL with useParams (a string).
  const { id } = useParams<{ id: string }>();
  const sessionId = Number(id);

  const [session, setSession] = useState<Session | null>(null);
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState<string | null>(null); // answer sent, reply not back yet
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Load the whole transcript from the server. This is what makes a page refresh safe:
  // nothing lives only in the browser.
  useEffect(() => {
    if (!ready) return;
    getSession(sessionId)
      .then(setSession)
      .catch((e) =>
        setError(
          e instanceof ApiError && e.status === 404
            ? "Interview not found."
            : String(e.message),
        ),
      );
  }, [ready, sessionId]);

  // Keep the newest message in view.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [session?.turns.length, pending]);

  async function send() {
    const text = draft;
    if (!session || pending !== null) return;
    setPending(text);
    setDraft("");
    setError(null);
    try {
      const result = await sendAnswer(session.id, text);
      // The server returns the answer as saved plus the reply: append both.
      setSession({
        ...session,
        status: result.status,
        turns: [...session.turns, ...result.turns],
      });
    } catch (e) {
      setDraft(text); // give the text back so nothing typed is lost
      setError(e instanceof Error ? e.message : "Could not send the answer");
      if (e instanceof ApiError && e.status === 409)
        setSession(await getSession(session.id));
    } finally {
      setPending(null);
    }
  }

  /** A spoken answer: the server transcribes it and answers like a typed one. */
  async function sendRecording(recording: Recording) {
    if (!session) return;
    setUploading(true);
    setError(null);
    try {
      const result = await uploadAudio(session.id, recording.blob);
      setSession({
        ...session,
        status: result.status,
        turns: [...session.turns, ...result.turns],
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not send the recording");
    } finally {
      setUploading(false);
    }
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    // Enter sends; Shift+Enter makes a new line.
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      send();
    }
  }

  if (error && !session) return <Message text={error} />;
  if (!session) return <Message text="Loading…" />;

  const finished = session.status !== "in_progress";

  return (
    <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col p-4">
      <header className="mb-4 flex items-center justify-between">
        <Link
          href="/dashboard"
          className="text-sm text-zinc-500 hover:underline"
        >
          ← Dashboard
        </Link>
        <span className="text-sm text-zinc-500">
          {finished ? "Finished" : "In progress"}
        </span>
      </header>

      <ol className="flex-1 space-y-3">
        {session.turns.map((turn) => (
          <Bubble key={turn.turn_index} turn={turn} />
        ))}
        {pending !== null && (
          <>
            <Bubble turn={{ speaker: "candidate", text: pending }} faded />
            <li className="text-sm text-zinc-500">Interviewer is thinking…</li>
          </>
        )}
      </ol>
      <div ref={bottomRef} />

      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}

      {finished ? (
        <p className="mt-4 rounded-lg bg-zinc-100 p-4 text-center text-sm dark:bg-zinc-800">
          The interview is over.{" "}
          <Link href="/dashboard" className="underline">
            Start another one
          </Link>
        </p>
      ) : (
        <div className="sticky bottom-0 mt-4 space-y-2 bg-background py-2">
          <TalkButton
            onRecorded={sendRecording}
            disabled={pending !== null || uploading}
          />
          {uploading && (
            <p className="text-sm text-zinc-500">Listening to your answer…</p>
          )}
          <div className="flex gap-2">
            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={onKeyDown}
              disabled={pending !== null}
              maxLength={4000}
              rows={3}
              placeholder="Type your answer… (Enter to send, Shift+Enter for a new line)"
              className="flex-1 resize-none rounded-md border border-zinc-300 bg-transparent px-3 py-2 outline-none focus:border-zinc-500 dark:border-zinc-700"
            />
            <button
              onClick={send}
              disabled={pending !== null}
              className="self-end rounded-md bg-zinc-900 px-4 py-2 font-medium text-white hover:bg-zinc-700 disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900"
            >
              Send
            </button>
          </div>
        </div>
      )}
    </main>
  );
}

function Bubble({
  turn,
  faded = false,
}: {
  turn: Pick<Turn, "speaker" | "text">;
  faded?: boolean;
}) {
  const mine = turn.speaker === "candidate";
  return (
    <li className={`flex ${mine ? "justify-end" : "justify-start"}`}>
      <p
        className={`max-w-[80%] whitespace-pre-wrap rounded-2xl px-4 py-2 ${
          mine
            ? "bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900"
            : "bg-zinc-100 dark:bg-zinc-800"
        } ${faded ? "opacity-60" : ""}`}
      >
        {turn.text}
      </p>
    </li>
  );
}

function Message({ text }: { text: string }) {
  return <p className="p-6 text-zinc-500">{text}</p>;
}
