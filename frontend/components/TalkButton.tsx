"use client";

import { type PointerEvent, useState } from "react";

import { type Recording, useRecorder } from "@/lib/useRecorder";

const MIN_RECORDING_MS = 1000; // the plan: reject recordings shorter than about 1 second

/** Hold to record, release to stop. Calls onRecorded with recordings of at least 1 second.
 * The same press/release handling as the mic test page, packaged for reuse. */
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

  return (
    <div className="space-y-1">
      <button
        type="button"
        onPointerDown={onPointerDown}
        onPointerUp={onRelease}
        onPointerCancel={onRelease}
        onContextMenu={(e) => e.preventDefault()}
        disabled={disabled}
        className={`w-full select-none touch-none rounded-full px-6 py-3 font-medium text-white disabled:opacity-50 ${
          isRecording
            ? "bg-red-600"
            : "bg-zinc-900 dark:bg-zinc-100 dark:text-zinc-900"
        }`}
      >
        {isRecording ? "● Recording… release to send" : "🎤 Hold to talk"}
      </button>
      {error && <p className="text-sm text-red-600">{error}</p>}
      {message && <p className="text-sm text-zinc-500">{message}</p>}
    </div>
  );
}
