"use client";
import { useEffect, useRef, useState } from "react";

export type Recording = { blob: Blob; mimeType: string; durationMs: number };

const PREFERRED_TYPES = ["audio/webm;codecs=opus", "audio/mp4", "audio/ogg;codecs=opus"];

export function useRecorder() {
  const [isRecording, setIsRecording] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // useRef: values that must survive re-renders but don't change what's on screen
  const streamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const startedAtRef = useRef(0);
  const holdingRef = useRef(false); // is the button held right now?

  useEffect(() => {
    // The function returned from an effect is its "cleanup": React runs it when the
    // component disappears (you navigate away). Empty [] = run once, clean up once.
    return () => {
      streamRef.current?.getTracks().forEach((track) => track.stop());
    };
  }, []);

  async function start() {
    setError(null); // clear the message from a previous attempt
    if (!navigator.mediaDevices?.getUserMedia) {
      setError("The microphone only works on https:// or http://localhost.");
      return;
    }

    holdingRef.current = true;

    if (!streamRef.current) {
      try {
        streamRef.current = await navigator.mediaDevices.getUserMedia({ audio: true });
      } catch (e) {
        const name = e instanceof DOMException ? e.name : "";
        if (name === "NotAllowedError") {
          setError("Microphone blocked. Click the 🔒 icon in the address bar and allow the microphone.");
        } else if (name === "NotFoundError") {
          setError("No microphone found. Plug one in and try again.");
        } else {
          setError("Could not start the microphone.");
        }
        holdingRef.current = false;
        return;
      }
    }

    // Released while the permission popup was open? Then don't start recording.
    if (!holdingRef.current) return;

    const mimeType = PREFERRED_TYPES.find((type) => MediaRecorder.isTypeSupported(type));

    const recorder = new MediaRecorder(streamRef.current, mimeType ? { mimeType } : undefined);
    chunksRef.current = []; // forget the previous recording
    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) chunksRef.current.push(e.data);
    };
    recorderRef.current = recorder;
    startedAtRef.current = Date.now();
    recorder.start();
    setIsRecording(true);
  }

  function stop(): Promise<Recording | null> {
    holdingRef.current = false; // tells a start() still waiting for permission: don't record
    const recorder = recorderRef.current;
    if (!recorder || recorder.state !== "recording") {
      return Promise.resolve(null);
    }

    return new Promise((resolve) => {
      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType });
        resolve({ blob, mimeType: recorder.mimeType, durationMs: Date.now() - startedAtRef.current });
      };
      recorder.stop();
      setIsRecording(false);
    });
  }

  return { isRecording, error, start, stop };
}
