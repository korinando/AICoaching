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
  reportFirstAudio,
  type Session,
  type Turn,
} from "@/lib/api";
import { useAudioQueue } from "@/lib/useAudioQueue";
import { useInterviewSocket } from "@/lib/useInterviewSocket";
import type { Recording } from "@/lib/useRecorder";
import { useRequireLogin } from "@/lib/useRequireLogin";
import { useTurnAudio } from "@/lib/useTurnAudio";
import type { ServerMessage } from "@/lib/wsMessages";

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
  // One answer and reply on their way, only for showing. session.turns stays what the server saved.
  const [pending, setPending] = useState<string | null>(null); // the answer, typed or transcribed
  const [reply, setReply] = useState(""); // the sentences that have arrived so far
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false); // recording sent, no transcript yet
  const [finishing, setFinishing] = useState(false); // came back to an answer still being worked on
  const bottomRef = useRef<HTMLDivElement>(null);
  const typedRef = useRef<string | null>(null); // to give it back if the server refuses it
  const givenBackRef = useRef<string | null>(null); // given back when the connection dropped
  const endOfSpeechRef = useRef<number | null>(null); // only set for a spoken answer
  const firstAudioRef = useRef<Promise<number | null> | null>(null);
  const { play, stop } = useTurnAudio();
  const queue = useAudioQueue();

  const busy = pending !== null || uploading || finishing;
  const { send: sendToSocket, lost } = useInterviewSocket(
    sessionId,
    session?.status === "in_progress",
    { onMessage: handleMessage, onLost: handleLost, beforeReconnect },
  );

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
  }, [session?.turns.length, pending, reply]);

  function handleMessage(message: ServerMessage) {
    switch (message.type) {
      case "transcript":
        typedRef.current = null;
        setUploading(false);
        setPending(message.text);
        break;
      case "interviewer_text":
        setReply((current) =>
          current ? `${current} ${message.text}` : message.text,
        );
        break;
      case "audio_chunk": {
        const scheduled = queue.enqueue(message.audio_base64);
        const endOfSpeech = endOfSpeechRef.current;
        if (endOfSpeech !== null && firstAudioRef.current === null) {
          firstAudioRef.current = scheduled.then((started) =>
            started ? performance.now() - endOfSpeech : null,
          );
        }
        break;
      }
      case "turn_complete":
        // Reported now and not at the first sound: the first sound can come before the server
        // has saved the turn. A lost measurement doesn't matter to the user, so it's ignored.
        void firstAudioRef.current?.then((ms) => {
          if (ms !== null) {
            reportFirstAudio(sessionId, message.turn_index, ms).catch(() => {});
          }
        });
        void finishTurn();
        break;
      case "session_ended":
        setSession((s) => s && { ...s, status: message.status });
        break;
      case "answer_in_progress":
        // The server did get it, so the copy in the box must not be sent a second time.
        forgetGivenBack();
        setError(null);
        setFinishing(true);
        break;
      case "error":
        setError(message.message);
        queue.stop(); // the reply's text is about to go too, so don't keep speaking it
        void finishTurn();
        break;
    }
  }

  function forgetGivenBack() {
    const text = givenBackRef.current;
    givenBackRef.current = null;
    setDraft((current) => (current === text ? "" : current));
  }

  function handleLost() {
    if (typedRef.current !== null) givenBackRef.current = typedRef.current;
    // A recording can't be given back. If it did arrive, answer_in_progress clears this.
    if (uploading)
      setError("If your answer doesn't appear, please say it again.");
    clearTurn(); // no reload yet: the server may be away, and beforeReconnect loads it anyway
  }

  /** The answer may have been saved while the connection was down: don't offer to send it again. */
  async function beforeReconnect() {
    const loaded = await getSession(sessionId);
    setSession(loaded);
    const lastAnswer = loaded.turns.findLast((t) => t.speaker === "candidate");
    if (lastAnswer?.text === givenBackRef.current) forgetGivenBack();
  }

  /** The reply is finished or failed: show what the server really saved. */
  async function finishTurn() {
    try {
      setSession(await getSession(sessionId));
    } catch {
      // Keep a message that's already there: it says what really went wrong.
      setError((current) => current ?? "Could not reload the interview.");
    }
    clearTurn();
  }

  /** Nothing is on its way any more. */
  function clearTurn() {
    // Still set only if the server never accepted it. Nothing typed is lost.
    if (typedRef.current !== null) setDraft(typedRef.current);
    typedRef.current = null;
    endOfSpeechRef.current = null;
    firstAudioRef.current = null;
    setPending(null);
    setReply("");
    setUploading(false);
    setFinishing(false);
  }

  /** Stop any sound that is still playing. */
  function prepareToAnswer() {
    stop();
    queue.stop();
  }

  function send() {
    const text = draft;
    if (!session || busy) return;
    prepareToAnswer();
    setError(null);
    if (!sendToSocket({ type: "text_answer", text })) {
      setError("Not connected yet. Please try again in a moment.");
      return;
    }
    givenBackRef.current = null;
    typedRef.current = text;
    setPending(text);
    setDraft("");
  }

  /** A spoken answer: the server transcribes it and answers like a typed one. */
  function sendRecording(recording: Recording) {
    if (!session) return;
    setError(null);
    if (!sendToSocket(recording.blob)) {
      setError(
        "Not connected, so that wasn't sent. Please say it again in a moment.",
      );
      return;
    }
    endOfSpeechRef.current = recording.stoppedAt;
    setUploading(true);
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
                ? () => {
                    queue.stop();
                    void play(session.id, turn.turn_index);
                  }
                : undefined
            }
          />
        ))}
        {pending !== null && (
          <>
            <Bubble turn={{ speaker: "candidate", text: pending }} faded />
            {reply ? (
              <Bubble turn={{ speaker: "interviewer", text: reply }} />
            ) : (
              <li className="text-sm text-zinc-500">
                Interviewer is thinking…
              </li>
            )}
          </>
        )}
      </ol>
      <div ref={bottomRef} />

      {finishing && (
        <p className="mt-2 text-sm text-zinc-500">
          Finishing your last answer…
        </p>
      )}
      {lost && !finished && (
        <p className="mt-2 text-sm text-amber-600">
          Connection lost. Reconnecting…
        </p>
      )}
      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}

      {finished ? (
        <p className="mt-4 rounded-lg bg-zinc-100 p-4 text-center text-sm dark:bg-zinc-800">
          The interview is over.{" "}
          <Link href={`/interview/${sessionId}/report`} className="underline">
            See your report
          </Link>{" "}
          or{" "}
          <Link href="/dashboard" className="underline">
            start another one
          </Link>
        </p>
      ) : (
        <div className="sticky bottom-0 mt-4 space-y-2 bg-background py-2">
          <TalkButton
            onRecorded={sendRecording}
            onPress={prepareToAnswer} // don't record the interviewer's voice through the speakers
            disabled={busy || lost}
          />
          {uploading && (
            <p className="text-sm text-zinc-500">Listening to your answer…</p>
          )}
          <div className="flex gap-2">
            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={onKeyDown}
              disabled={busy}
              maxLength={4000}
              rows={3}
              placeholder="Type your answer… (Enter to send, Shift+Enter for a new line)"
              className="flex-1 resize-none rounded-md border border-zinc-300 bg-transparent px-3 py-2 outline-none focus:border-zinc-500 dark:border-zinc-700"
            />
            <button
              onClick={send}
              disabled={busy || lost}
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
