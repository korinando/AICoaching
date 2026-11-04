"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { accessToken, API_URL } from "./api";
import type { ClientMessage, ServerMessage } from "./wsMessages";

type Handlers = {
  onMessage: (message: ServerMessage) => void;
  onLost: () => void; // the connection closed and the server didn't mean to end it
  // Before each new try. Loading anything through apiFetch also renews an expired token, which
  // is why a closed 4401 needs nothing special: the next try simply logs in with the new one.
  beforeReconnect: () => Promise<void>;
};

const CLOSE_NORMAL = 1000;
const CLOSE_NOT_FOUND = 4404; // trying again can't help
const RETRY_MS = 2000;

/** One WebSocket for one interview, open while `enabled` is true. Reconnects by itself if the
 * connection is lost, and `lost` says that it's trying. */
export function useInterviewSocket(
  sessionId: number,
  enabled: boolean,
  handlers: Handlers,
) {
  const socketRef = useRef<WebSocket | null>(null);
  const [lost, setLost] = useState(false);
  // Always the newest handlers, without reconnecting each time the page re-renders.
  const handlersRef = useRef(handlers);
  useEffect(() => {
    handlersRef.current = handlers;
  });

  useEffect(() => {
    if (!enabled) return;
    let stopped = false; // this page closed it on purpose (see the end of this effect)
    let timer: ReturnType<typeof setTimeout> | undefined;

    function connect() {
      const url = `${API_URL.replace(/^http/, "ws")}/ws/sessions/${sessionId}`;
      const socket = new WebSocket(url);
      socket.onopen = () => {
        const auth: ClientMessage = {
          type: "auth",
          token: accessToken() ?? "",
        };
        socket.send(JSON.stringify(auth));
        setLost(false);
      };
      socket.onmessage = (event) => {
        handlersRef.current.onMessage(JSON.parse(event.data) as ServerMessage);
      };
      socket.onclose = (event) => {
        if (stopped) return;
        if (event.code === CLOSE_NORMAL || event.code === CLOSE_NOT_FOUND) {
          return;
        }
        setLost(true);
        handlersRef.current.onLost();
        timer = setTimeout(reconnect, RETRY_MS);
      };
      socketRef.current = socket;
    }

    async function reconnect() {
      try {
        await handlersRef.current.beforeReconnect();
      } catch {
        // The server is still away. Trying the socket now would only fail too.
        if (!stopped) timer = setTimeout(reconnect, RETRY_MS);
        return;
      }
      if (!stopped) connect();
    }

    connect();
    return () => {
      stopped = true;
      clearTimeout(timer);
      socketRef.current?.close();
      socketRef.current = null;
    };
  }, [sessionId, enabled]);

  /** A message, or a recording as a binary frame. False if the connection isn't open. */
  const send = useCallback((message: ClientMessage | Blob): boolean => {
    const socket = socketRef.current;
    if (socket?.readyState !== WebSocket.OPEN) return false;
    socket.send(message instanceof Blob ? message : JSON.stringify(message));
    return true;
  }, []);

  return { send, lost };
}
