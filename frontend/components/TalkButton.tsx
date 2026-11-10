"use client";

import { type PointerEvent, useState } from "react";

import { type Recording, useRecorder } from "@/lib/useRecorder";

import { MicIcon } from "./icons";

const MIN_RECORDING_MS = 1000; // the plan: reject recordings shorter than about 1 second

/** Hold to record, release to stop. Calls onRecorded with recordings of at least 1 second.
 * The same press/release handling as the mic test page, packaged for reuse. Its messages float
 * above it, so it fits in a row of buttons. */
export function TalkButton({
  onRecorded,
  onPress,
  disabled = false,
}: {
  onRecorded: (recording: Recording) => void;
  onPress?: () => void;
  disabled?: boolean;
}) {
  const { isRecording, error, start, stop } = useRecorder();
  const [message, setMessage] = useState<string | null>(null);

  function onPointerDown(e: PointerEvent<HTMLButtonElement>) {
    if (disabled) return;
    e.currentTarget.setPointerCapture(e.pointerId); // release outside the button still counts
    setMessage(null);
    onPress?.();
    void start(); // "void": start on purpose without waiting; release calls stop()
  }

  async function onRelease() {
    const rec = await stop();
    if (!rec) return;
    if (rec.durationMs < MIN_RECORDING_MS) {
      setMessage("Too short: hold the button while you speak.");
      return;
    }
    onRecorded(rec);
  }

  const note = error ?? message;

  return (
    <div className="relative">
      {note && (
        <p
          role="status"
          className={`absolute bottom-full right-0 mb-2 w-64 rounded-lg border border-line bg-surface px-3 py-2 text-xs shadow-md ${
            error ? "text-danger" : "text-muted"
          }`}
        >
          {note}
        </p>
      )}
      <button
        type="button"
        onPointerDown={onPointerDown}
        onPointerUp={onRelease}
        onPointerCancel={onRelease}
        onContextMenu={(e) => e.preventDefault()}
        disabled={disabled}
        className={`flex h-10 select-none touch-none items-center gap-2 rounded-full px-4 text-sm font-medium transition-colors disabled:opacity-40 ${
          isRecording
            ? "bg-danger text-white"
            : "bg-accent text-accent-fg hover:bg-accent-hover"
        }`}
      >
        {isRecording ? (
          <>
            <span className="relative flex h-2.5 w-2.5">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-white opacity-75 motion-reduce:animate-none" />
              <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-white" />
            </span>
            Release to send
          </>
        ) : (
          <>
            <MicIcon className="h-4 w-4" />
            Hold to talk
          </>
        )}
      </button>
    </div>
  );
}
