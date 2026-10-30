"use client";

import { useState, type PointerEvent } from "react";
import { type Recording, useRecorder } from "@/lib/useRecorder";

export default function MicTestPage() {
  const { isRecording, error, start, stop } = useRecorder();
  const [recording, setRecording] = useState<Recording | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  function onPointerDown(e: PointerEvent<HTMLButtonElement>) {
    e.currentTarget.setPointerCapture(e.pointerId); // release outside the button still counts
    setMessage(null);
    start();
  }

  async function onRelease() {
    const rec = await stop();
    if (!rec) return;
    if (rec.durationMs < 1000) {
      setMessage("Too short: hold the button while you speak.");
      return;
    }
    setRecording(rec);
  }

  return (
    <main className="mx-auto max-w-md space-y-4 p-6">
      <h1 className="text-xl font-semibold">Microphone test</h1>
      <button
        onPointerDown={onPointerDown}
        onPointerUp={onRelease}
        onPointerCancel={onRelease}
        onContextMenu={(e) => e.preventDefault()}
        className="w-full select-none touch-none rounded-full bg-zinc-900 px-6 py-4 font-medium text-white dark:bg-zinc-100 dark:text-zinc-900"
      >
        {isRecording ? "Recording… release to stop" : "Hold to talk"}
      </button>
      {error && <p className="text-sm text-red-600">{error}</p>}
      {message && <p className="text-sm text-zinc-500">{message}</p>}
      {recording && (
        <div className="space-y-2">
          <audio controls src={URL.createObjectURL(recording.blob)} className="w-full" />
          <p className="text-sm text-zinc-500">
            {recording.mimeType} · {(recording.blob.size / 1024).toFixed(1)} KB ·{" "}
            {(recording.durationMs / 1000).toFixed(1)} s
          </p>
        </div>
      )}
    </main>
  );
}
