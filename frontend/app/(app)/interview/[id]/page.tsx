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

import { Logo, ReportIcon, SendIcon, SpeakerIcon } from "@/components/icons";
import { useOpenNewInterview } from "@/components/NewInterview";
import { TalkButton } from "@/components/TalkButton";
import {
  ApiError,
  getSession,
  reportFirstAudio,
  type Session,
  type Turn,
} from "@/lib/api";
import { useAppData } from "@/lib/appData";
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
  const { sessions, refreshSessions } = useAppData();
  const openNewInterview = useOpenNewInterview();

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
        void refreshSessions(); // the sidebar shows it as finished, then scoring
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

  function endInterview() {
    const message =
      "End the interview now? You can't continue it afterwards. You'll get a report if you've given at least 3 answers.";
    if (!window.confirm(message)) return;
    prepareToAnswer();
    setError(null);
    if (!sendToSocket({ type: "end_session" })) {
      setError("Not connected yet. Please try again in a moment.");
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
  const role = sessions?.find((s) => s.id === sessionId)?.role ?? "Interview";
  const answers = session.turns.filter((t) => t.speaker === "candidate").length;

  return (
    <main className="flex min-h-full flex-col">
      <header className="sticky top-0 z-10 flex items-center justify-between gap-3 border-b border-line bg-background/90 px-4 py-3 backdrop-blur md:px-6">
        <div className="min-w-0">
          <h1 className="truncate font-semibold">{role}</h1>
          <p className="text-xs text-muted">
            {finished ? (
              "Finished"
            ) : (
              <span className="inline-flex items-center gap-1.5">
                <span className="h-1.5 w-1.5 rounded-full bg-accent" />
                In progress
              </span>
            )}
            {" · "}
            {answers} {answers === 1 ? "answer" : "answers"}
          </p>
        </div>
        {finished ? (
          <Link
            href={`/interview/${sessionId}/report`}
            className="flex shrink-0 items-center gap-1.5 rounded-lg bg-accent px-3 py-1.5 text-sm font-medium text-accent-fg hover:bg-accent-hover"
          >
            <ReportIcon className="h-4 w-4" />
            View report
          </Link>
        ) : (
          <button
            type="button"
            onClick={endInterview}
            disabled={busy || lost}
            className="shrink-0 rounded-lg border border-line px-3 py-1.5 text-sm text-muted hover:border-danger hover:text-danger disabled:opacity-50"
          >
            End interview
          </button>
        )}
      </header>

      <ol className="mx-auto w-full max-w-3xl flex-1 space-y-6 px-4 py-6 md:px-6">
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
              <Thinking />
            )}
          </>
        )}
        {uploading && pending === null && (
          <li className="flex justify-end">
            <p className="rounded-2xl bg-accent-soft px-4 py-2 text-sm text-accent">
              Listening to your answer…
            </p>
          </li>
        )}
      </ol>
      <div ref={bottomRef} />

      <div className="sticky bottom-0 bg-gradient-to-t from-background from-70% to-transparent px-4 pb-4 pt-6 md:px-6">
        <div className="mx-auto w-full max-w-3xl space-y-2">
          {finishing && (
            <p className="text-sm text-muted">Finishing your last answer…</p>
          )}
          {lost && !finished && (
            <p className="text-sm text-amber-600 dark:text-amber-400">
              Connection lost. Reconnecting…
            </p>
          )}
          {error && (
            <p role="alert" className="text-sm text-danger">
              {error}
            </p>
          )}

          {finished ? (
            <div className="flex flex-col items-center gap-3 rounded-2xl border border-line bg-surface p-5 text-center sm:flex-row sm:justify-between sm:text-left">
              <p className="text-sm">
                <span className="font-medium">The interview is over.</span>{" "}
                <span className="text-muted">
                  Your report is ready a minute or two after it ends.
                </span>
              </p>
              <div className="flex shrink-0 gap-2">
                <button
                  type="button"
                  onClick={openNewInterview}
                  className="rounded-lg border border-line px-3 py-1.5 text-sm hover:bg-surface-3"
                >
                  New interview
                </button>
                <Link
                  href={`/interview/${sessionId}/report`}
                  className="rounded-lg bg-accent px-3 py-1.5 text-sm font-medium text-accent-fg hover:bg-accent-hover"
                >
                  See your report
                </Link>
              </div>
            </div>
          ) : (
            <div className="rounded-2xl border border-line bg-surface shadow-sm focus-within:border-accent">
              <label htmlFor="answer" className="sr-only">
                Your answer
              </label>
              <textarea
                id="answer"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={onKeyDown}
                disabled={busy}
                maxLength={4000}
                rows={2}
                placeholder="Hold the mic to answer out loud, or type here…"
                className="block w-full resize-none bg-transparent px-4 pt-3 outline-none placeholder:text-muted disabled:opacity-60"
              />
              <div className="flex items-center justify-between gap-2 px-2 pb-2">
                <p className="hidden pl-2 text-xs text-muted sm:block">
                  Enter to send · Shift+Enter for a new line
                </p>
                <div className="ml-auto flex items-center gap-2">
                  <TalkButton
                    onRecorded={sendRecording}
                    onPress={prepareToAnswer} // don't record the interviewer's voice through the speakers
                    disabled={busy || lost}
                  />
                  <button
                    onClick={send}
                    disabled={busy || lost || draft.trim() === ""}
                    aria-label="Send typed answer"
                    className="flex h-10 w-10 items-center justify-center rounded-full bg-foreground text-background hover:opacity-80 disabled:opacity-30"
                  >
                    <SendIcon className="h-5 w-5" />
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
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
  if (turn.speaker === "candidate") {
    return (
      <li className="flex justify-end">
        <p
          className={`max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-accent-soft px-4 py-2.5 ${
            faded ? "opacity-60" : ""
          }`}
        >
          {turn.text}
        </p>
      </li>
    );
  }
  return (
    <li className="group flex gap-3">
      <InterviewerAvatar />
      <div className="min-w-0 flex-1 space-y-1 pt-1">
        <p className="whitespace-pre-wrap leading-relaxed">{turn.text}</p>
        {onPlay && (
          <button
            type="button"
            onClick={onPlay}
            aria-label="Play this message again"
            title="Play again"
            className="-ml-1.5 rounded-md p-1.5 text-muted opacity-70 hover:bg-surface-3 hover:text-foreground group-hover:opacity-100"
          >
            <SpeakerIcon className="h-4 w-4" />
          </button>
        )}
      </div>
    </li>
  );
}

function InterviewerAvatar() {
  return (
    <span aria-hidden className="mt-0.5 shrink-0">
      <Logo className="h-8 w-8" />
    </span>
  );
}

function Thinking() {
  return (
    <li className="flex items-center gap-3" aria-live="polite">
      <InterviewerAvatar />
      <span className="sr-only">The interviewer is thinking</span>
      <span aria-hidden className="flex gap-1">
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className="thinking-dot h-2 w-2 rounded-full bg-muted"
            style={{ animationDelay: `${i * 0.15}s` }}
          />
        ))}
      </span>
    </li>
  );
}

function Message({ text }: { text: string }) {
  return <p className="p-6 text-muted">{text}</p>;
}
