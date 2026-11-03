"use client";

import { useCallback, useEffect, useRef } from "react";

import { getTurnAudio } from "./api";

/** Plays one turn's audio at a time. Failures are silent on purpose: the text is always on
 * screen, and browsers may refuse to play sound before the user has clicked on the page. */
export function useTurnAudio() {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const urlRef = useRef<string | null>(null);
  const requestRef = useRef(0); // the newest request; older ones must not start playing

  const stop = useCallback(() => {
    requestRef.current += 1;
    audioRef.current?.pause();
    audioRef.current = null;
    // A blob URL keeps the file in memory until it's released.
    if (urlRef.current) URL.revokeObjectURL(urlRef.current);
    urlRef.current = null;
  }, []);

  const play = useCallback(
    /** Resolves true if the sound really started. */
    async (sessionId: number, turnIndex: number): Promise<boolean> => {
      stop();
      const request = requestRef.current;
      try {
        const blob = await getTurnAudio(sessionId, turnIndex);
        // Something newer happened while downloading (e.g. the user started talking).
        if (request !== requestRef.current) return false;
        urlRef.current = URL.createObjectURL(blob);
        audioRef.current = new Audio(urlRef.current);
        await audioRef.current.play(); // resolves when the sound has really started
        return true;
      } catch {
        // No sound this time; the text is on screen and the 🔊 button can try again.
        return false;
      }
    },
    [stop],
  );

  useEffect(() => stop, [stop]); // stop the sound when leaving the page

  return { play, stop };
}
