"use client";

import { useCallback, useEffect, useRef } from "react";

import { accessToken, API_URL } from "./api";
import type { ClientMessage, ServerMessage } from "./wsMessages";

type Handlers = {
  onMessage: (message: ServerMessage) => void;
  onLost: () => void; // the connection closed and the server didn't mean to end it
};

const CLOSE_NORMAL = 1000;

/** One WebSocket for one interview, open while `enabled` is true. */
export function useInterviewSocket(
  sessionId: number,
  enabled: boolean,
  handlers: Handlers,
) {
  const socketRef = useRef<WebSocket | null>(null);
  // Always the newest handlers, without reconnecting each time the page re-renders.
  const handlersRef = useRef(handlers);
  useEffect(() => {
    handlersRef.current = handlers;
  });

  useEffect(() => {
    if (!enabled) return;
    const url = `${API_URL.replace(/^http/, "ws")}/ws/sessions/${sessionId}`;
    const socket = new WebSocket(url);
    socket.onopen = () => {
      const auth: ClientMessage = { type: "auth", token: accessToken() ?? "" };
      socket.send(JSON.stringify(auth));
    };
    socket.onmessage = (event) => {
      handlersRef.current.onMessage(JSON.parse(event.data) as ServerMessage);
    };
    socket.onclose = (event) => {
      // socketRef is empty if this page closed it on purpose (see below).
      if (socketRef.current === socket && event.code !== CLOSE_NORMAL) {
        handlersRef.current.onLost();
      }
    };
    socketRef.current = socket;
    return () => {
      socketRef.current = null;
      socket.close();
    };
  }, [sessionId, enabled]);

  /** A message, or a recording as a binary frame. False if the connection isn't open. */
  const send = useCallback((message: ClientMessage | Blob): boolean => {
    const socket = socketRef.current;
    if (socket?.readyState !== WebSocket.OPEN) return false;
    socket.send(message instanceof Blob ? message : JSON.stringify(message));
    return true;
  }, []);

  return { send };
}
