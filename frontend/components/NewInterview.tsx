"use client";

import { useRouter } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";

import { createSession, listTemplates, type Template } from "@/lib/api";
import { useAppData } from "@/lib/appData";

import { ArrowUpRightIcon, CloseIcon } from "./icons";

const OpenContext = createContext<(() => void) | null>(null);

/** Any page or the sidebar can call this to open the interview picker. */
export function useOpenNewInterview(): () => void {
  const open = useContext(OpenContext);
  if (!open) throw new Error("useOpenNewInterview needs NewInterviewProvider");
  return open;
}

/** Holds the "New interview" pop-up, so it opens from the sidebar and from the home page alike.
 * It's a native <dialog>: the browser handles Esc, keeps keyboard focus inside it while it's
 * open, and tells screen readers it's a dialog. */
export function NewInterviewProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [isOpen, setIsOpen] = useState(false);
  const open = useCallback(() => {
    dialogRef.current?.showModal();
    setIsOpen(true);
  }, []);

  return (
    <OpenContext value={open}>
      {children}
      <dialog
        ref={dialogRef}
        onClose={() => setIsOpen(false)}
        // A click on the dimmed backdrop lands on the <dialog> itself: close it.
        onClick={(e) =>
          e.target === dialogRef.current && dialogRef.current?.close()
        }
        aria-labelledby="new-interview-title"
        className="m-auto w-[min(44rem,calc(100%-2rem))] rounded-2xl border border-line bg-background p-0 text-foreground shadow-2xl backdrop:bg-black/50"
      >
        {isOpen && <Picker onClose={() => dialogRef.current?.close()} />}
      </dialog>
    </OpenContext>
  );
}

function Picker({ onClose }: { onClose: () => void }) {
  const router = useRouter();
  const { refreshSessions } = useAppData();
  const [templates, setTemplates] = useState<Template[] | null>(null);
  const [startingId, setStartingId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listTemplates()
      .then(setTemplates)
      .catch(() =>
        setError("Could not load the interviews. Please try again."),
      );
  }, []);

  async function start(templateId: number) {
    setStartingId(templateId);
    setError(null);
    try {
      const session = await createSession(templateId); // includes the opening question (LLM call)
      void refreshSessions();
      onClose();
      router.push(`/interview/${session.id}`);
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Could not start the interview",
      );
      setStartingId(null);
    }
  }

  return (
    <div className="max-h-[85dvh] overflow-y-auto p-5 md:p-6">
      <div className="mb-1 flex items-start justify-between gap-4">
        <h2 id="new-interview-title" className="text-xl font-semibold">
          Choose an interview
        </h2>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="-mr-1.5 -mt-1 rounded-md p-1.5 text-muted hover:bg-surface-3"
        >
          <CloseIcon />
        </button>
      </div>
      <p className="mb-5 text-sm text-muted">
        Each interview picks 5 topics at random, so no two are the same. It
        takes about 10 minutes.
      </p>

      {error && (
        <p role="alert" className="mb-3 text-sm text-danger">
          {error}
        </p>
      )}

      {templates === null ? (
        <div className="space-y-3">
          {[0, 1, 2, 3, 4].map((i) => (
            <div
              key={i}
              className="h-20 animate-pulse rounded-xl bg-surface-3"
            />
          ))}
        </div>
      ) : (
        <ul className="space-y-3">
          {templates.map((t) => (
            <li key={t.id}>
              <button
                type="button"
                onClick={() => start(t.id)}
                disabled={startingId !== null}
                className="group flex w-full items-start gap-4 rounded-xl border border-line bg-surface p-4 text-left transition-colors hover:border-accent disabled:cursor-wait disabled:opacity-60"
              >
                <span className="min-w-0 flex-1">
                  <span className="flex flex-wrap items-center gap-2">
                    <span className="font-semibold">{t.role}</span>
                    <span className="rounded-md bg-accent-soft px-1.5 py-0.5 text-xs font-medium text-accent">
                      {t.interview_type === "behavioral"
                        ? "Behavioural"
                        : "Technical"}
                    </span>
                  </span>
                  <span className="mt-1 block text-sm text-muted">
                    {startingId === t.id
                      ? "Preparing your interviewer…"
                      : t.summary}
                  </span>
                </span>
                <ArrowUpRightIcon className="mt-1 h-5 w-5 shrink-0 text-muted transition-colors group-hover:text-accent" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
