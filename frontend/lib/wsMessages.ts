// Every message on the live interview WebSocket: the same shapes as
// backend/app/api/ws_messages.py. backend/tests/test_ws_messages.py fails if the two differ.
//
// A text frame is one JSON object. A binary frame from the browser is a recording (the plan's
// audio_answer), so it has no type here.

import type { SessionStatus } from "./api";

// ---- Client to server ----------------------------------------------------------------------

export type ClientMessage =
  | { type: "auth"; token: string }
  | { type: "text_answer"; text: string }
  | { type: "end_session" };

// ---- Server to client ----------------------------------------------------------------------

export type ErrorCode =
  | "unauthorized"
  | "not_found"
  | "interview_closed"
  | "invalid_message"
  | "invalid_audio"
  | "no_speech"
  | "busy"
  | "server_error";

// Writing `switch (message.type)` narrows each case to that message's fields, so reading a
// field that message doesn't have is a compile error.
export type ServerMessage =
  | { type: "transcript"; turn_index: number; text: string }
  | { type: "interviewer_text"; turn_index: number; seq: number; text: string }
  | {
      type: "audio_chunk";
      turn_index: number;
      seq: number;
      audio_base64: string;
    }
  | { type: "turn_complete"; turn_index: number }
  | { type: "answer_in_progress" }
  | { type: "session_ended"; status: Exclude<SessionStatus, "in_progress"> }
  | { type: "error"; code: ErrorCode; message: string };
