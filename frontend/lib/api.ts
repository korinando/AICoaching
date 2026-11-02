// Talks to the FastAPI backend. Every request goes through apiFetch(), which adds the login
// token and, when the access token has expired, gets a new one with the refresh token.

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ---- Types: the same shapes as backend/app/api/schemas.py ----------------------------------

export type User = {
  id: number;
  email: string;
  name: string;
  created_at: string;
};

export type Template = {
  id: number;
  slug: string;
  role: string;
  level: string;
  interview_type: string;
  topics: string[];
  max_main_questions: number;
};

export type Turn = {
  turn_index: number;
  speaker: "interviewer" | "candidate";
  text: string;
  created_at: string;
  has_audio: boolean; // true: getTurnAudio can play it
};

export type SessionStatus = "in_progress" | "completed" | "abandoned";

export type Session = {
  id: number;
  template_id: number;
  status: SessionStatus;
  started_at: string;
  ended_at: string | null;
  turns: Turn[];
};

export type AnswerResult = { status: SessionStatus; turns: Turn[] };

type TokenPair = { access_token: string; refresh_token: string };

// ---- Token storage -------------------------------------------------------------------------
// localStorage keeps you logged in after a refresh or a closed tab. Trade-off: any script
// running on this page can read it, so an XSS bug could steal the tokens. The safer option
// (httpOnly cookies set by the backend) needs CSRF protection too; noted for Week 7.

const ACCESS_KEY = "access_token";
const REFRESH_KEY = "refresh_token";

function saveTokens(tokens: TokenPair) {
  localStorage.setItem(ACCESS_KEY, tokens.access_token);
  localStorage.setItem(REFRESH_KEY, tokens.refresh_token);
}

export function logout() {
  localStorage.removeItem(ACCESS_KEY);
  localStorage.removeItem(REFRESH_KEY);
}

export function isLoggedIn(): boolean {
  return localStorage.getItem(REFRESH_KEY) !== null;
}

// ---- Errors --------------------------------------------------------------------------------

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

/** FastAPI errors look like {"detail": "..."} or, for 422, {"detail": [{"msg": ...}, ...]}. */
async function errorFrom(response: Response): Promise<ApiError> {
  let message = `Request failed (${response.status})`;
  try {
    const body = await response.json();
    if (typeof body.detail === "string") message = body.detail;
    else if (Array.isArray(body.detail))
      message = body.detail.map((d: { msg: string }) => d.msg).join("; ");
  } catch {
    // Not JSON: keep the generic message.
  }
  return new ApiError(response.status, message);
}

// ---- The one fetch wrapper -----------------------------------------------------------------

// If several requests get a 401 at the same moment, they share one refresh call instead of
// each trading the refresh token separately.
let refreshing: Promise<boolean> | null = null;

async function refreshTokens(): Promise<boolean> {
  const refreshToken = localStorage.getItem(REFRESH_KEY);
  if (!refreshToken) return false;
  const response = await fetch(`${API_URL}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  if (!response.ok) {
    logout(); // refresh token expired or invalid: the user must log in again
    return false;
  }
  saveTokens(await response.json());
  return true;
}

async function apiFetch<T>(
  path: string,
  options: { method?: string; body?: unknown; blob?: boolean } = {},
): Promise<T> {
  // A file upload (FormData) is sent as it is, WITHOUT a Content-Type header: the browser then
  // writes "multipart/form-data; boundary=..." itself, and the boundary (the marker between
  // the parts) can't be known in advance. Everything else is sent as JSON.
  const isForm = options.body instanceof FormData;
  const send = () =>
    fetch(`${API_URL}${path}`, {
      method: options.method ?? "GET",
      headers: {
        ...(!isForm && { "Content-Type": "application/json" }),
        ...(localStorage.getItem(ACCESS_KEY) && {
          Authorization: `Bearer ${localStorage.getItem(ACCESS_KEY)}`,
        }),
      },
      body:
        options.body === undefined
          ? undefined
          : isForm
            ? (options.body as FormData)
            : JSON.stringify(options.body),
    });

  let response = await send();
  // Access token expired (15 min)? Refresh once, then retry the same request once.
  if (response.status === 401 && localStorage.getItem(REFRESH_KEY)) {
    refreshing ??= refreshTokens().finally(() => (refreshing = null));
    if (await refreshing) response = await send();
  }
  if (!response.ok) throw await errorFrom(response);
  return (options.blob ? response.blob() : response.json()) as Promise<T>;
}

// ---- One function per endpoint -------------------------------------------------------------

export async function login(email: string, password: string): Promise<void> {
  saveTokens(
    await apiFetch<TokenPair>("/auth/login", {
      method: "POST",
      body: { email, password },
    }),
  );
}

export async function register(
  email: string,
  password: string,
  name: string,
): Promise<void> {
  await apiFetch<User>("/auth/register", {
    method: "POST",
    body: { email, password, name },
  });
  await login(email, password); // registering logs you in straight away
}

export const getMe = () => apiFetch<User>("/auth/me");

export const listTemplates = () => apiFetch<Template[]>("/templates");

export const createSession = (templateId: number) =>
  apiFetch<Session>("/sessions", {
    method: "POST",
    body: { template_id: templateId },
  });

export const getSession = (id: number) => apiFetch<Session>(`/sessions/${id}`);

export const sendAnswer = (id: number, text: string) =>
  apiFetch<AnswerResult>(`/sessions/${id}/answer`, {
    method: "POST",
    body: { text },
  });

/** The audio of one turn, as a file in memory. Fetched here rather than with <audio src>,
 * because a plain src can't send the login token. */
export const getTurnAudio = (sessionId: number, turnIndex: number) =>
  apiFetch<Blob>(`/sessions/${sessionId}/turns/${turnIndex}/audio`, {
    blob: true,
  });

/** A spoken answer: the server transcribes it and answers like sendAnswer. */
export function uploadAudio(id: number, blob: Blob) {
  const form = new FormData();
  // "audio" must match the backend parameter name. The file name is only a label; the
  // format travels as the blob's type (e.g. "audio/webm;codecs=opus").
  form.append("audio", blob, "answer");
  return apiFetch<AnswerResult>(`/sessions/${id}/audio`, {
    method: "POST",
    body: form,
  });
}
