"use client";

import { useEffect, useState } from "react";

type Sentence = { url: string; started: (played: boolean) => void };

function toBlobUrl(base64: string): string {
  const bytes = Uint8Array.from(atob(base64), (c) => c.charCodeAt(0));
  return URL.createObjectURL(new Blob([bytes], { type: "audio/wav" }));
}

/** Plays sentences one after another: each starts when the last one has ended, so they never
 * overlap. <audio> elements, the same as the replay button: the Web Audio API reported that it
 * was playing but was silent on a real browser (Week 4 Step 6). */
class AudioQueue {
  private waiting: Sentence[] = [];
  private current: { audio: HTMLAudioElement; url: string } | null = null;

  /** Resolves true when this sentence's sound really starts, false if it never does. */
  enqueue(audioBase64: string): Promise<boolean> {
    return new Promise((started) => {
      this.waiting.push({ url: toBlobUrl(audioBase64), started });
      if (!this.current) this.playNext();
    });
  }

  stop() {
    for (const sentence of this.waiting) {
      URL.revokeObjectURL(sentence.url); // a blob URL keeps the file in memory until released
      sentence.started(false);
    }
    this.waiting = [];
    this.current?.audio.pause();
    this.finishCurrent();
  }

  private playNext() {
    const sentence = this.waiting.shift();
    if (!sentence) return;
    const audio = new Audio(sentence.url);
    this.current = { audio, url: sentence.url };
    const next = () => {
      // stop() may have moved on already; this sound must not start the next one then.
      if (this.current?.audio !== audio) return;
      this.finishCurrent();
      this.playNext();
    };
    audio.onended = next;
    audio.play().then(
      () => sentence.started(true),
      () => {
        // A bad chunk must not stop the ones after it; the text is on screen anyway.
        sentence.started(false);
        next();
      },
    );
  }

  private finishCurrent() {
    if (this.current) URL.revokeObjectURL(this.current.url);
    this.current = null;
  }
}

/** One queue for as long as the page is open. Stops the sound when leaving the page. */
export function useAudioQueue() {
  const [queue] = useState(() => new AudioQueue());
  useEffect(() => () => queue.stop(), [queue]);
  return queue;
}
