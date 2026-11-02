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
  type AnswerResult,
  ApiError,
  getSession,
  sendAnswer,
  type Session,
  type Turn,
  uploadAudio,
} from "@/lib/api";
import type { Recording } from "@/lib/useRecorder";
import { useRequireLogin } from "@/lib/useRequireLogin";
import { useTurnAudio } from "@/lib/useTurnAudio";

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
  const { play, stop } = useTurnAudio();

  // Load the whole transcript from the server. This is what makes a page refresh safe:
  // nothing lives only in the browser.
  useEffect(() => {
    if (!ready) return;
    getSession(sessionId)
      .then((loaded) => {
        setSession(loaded);
        // A brand-new interview: speak the opening question. Later on, a refresh stays quiet.
        if (loaded.turns.length === 1 && loaded.turns[0].has_audio) {
          void play(sessionId, 0);
        }
      })
      .catch((e) =>
        setError(
          e instanceof ApiError && e.status === 404
            ? "Interview not found."
            : String(e.message),
        ),
      );
  }, [ready, sessionId, play]);

  // Keep the newest message in view.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [session?.turns.length, pending]);

  /** Add the new turns to the chat and speak the interviewer's reply. */
  function showResult(current: Session, result: AnswerResult) {
    setSession({
      ...current,
      status: result.status,
      turns: [...current.turns, ...result.turns],
    });
    const reply = result.turns.at(-1);
    if (reply?.has_audio) void play(current.id, reply.turn_index);
  }

  async function send() {
    const text = draft;
    if (!session || pending !== null) return;
    setPending(text);
    setDraft("");
    setError(null);
    try {
      // The server returns the answer as saved plus the reply.
      showResult(session, await sendAnswer(session.id, text));
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
      showResult(session, await uploadAudio(session.id, recording.blob));
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
          <Bubble
            key={turn.turn_index}
            turn={turn}
            onPlay={
              turn.has_audio
                ? () => void play(session.id, turn.turn_index)
                : undefined
            }
          />
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
            onPress={stop} // don't record the interviewer's voice through the speakers
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
  onPlay,
}: {
  turn: Pick<Turn, "speaker" | "text">;
  faded?: boolean;
  onPlay?: () => void;
}) {
  const mine = turn.speaker === "candidate";
  return (
    <li className={`flex items-center gap-1 ${mine ? "flex-row-reverse" : ""}`}>
      <p
        className={`max-w-[80%] whitespace-pre-wrap rounded-2xl px-4 py-2 ${
          mine
            ? "bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900"
            : "bg-zinc-100 dark:bg-zinc-800"
        } ${faded ? "opacity-60" : ""}`}
      >
        {turn.text}
      </p>
      {onPlay && (
        <button
          type="button"
          onClick={onPlay}
          aria-label="Play this message"
          className="rounded p-1 text-sm opacity-60 hover:opacity-100"
        >
          🔊
        </button>
      )}
    </li>
  );
}

function Message({ text }: { text: string }) {
  return <p className="p-6 text-zinc-500">{text}</p>;
}
