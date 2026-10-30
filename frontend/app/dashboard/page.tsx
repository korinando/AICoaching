"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { createSession, getMe, listTemplates, logout, type Template, type User } from "@/lib/api";
import { useRequireLogin } from "@/lib/useRequireLogin";

export default function DashboardPage() {
  const ready = useRequireLogin();
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [startingId, setStartingId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!ready) return;
    // Both requests at once, not one after the other.
    Promise.all([getMe(), listTemplates()])
      .then(([me, list]) => {
        setUser(me);
        setTemplates(list);
      })
      .catch(() => {
        // Even the refresh token failed: the login has really expired.
        logout();
        router.replace("/login");
      });
  }, [ready, router]);

  async function start(templateId: number) {
    setStartingId(templateId);
    setError(null);
    try {
      const session = await createSession(templateId); // includes the opening question (LLM call)
      router.push(`/interview/${session.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start the interview");
      setStartingId(null);
    }
  }

  if (!user) return <p className="p-6 text-zinc-500">Loading…</p>;

  return (
    <main className="mx-auto w-full max-w-3xl space-y-6 p-6">
      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Hi {user.name}, choose an interview</h1>
        <button
          onClick={() => {
            logout();
            router.replace("/login");
          }}
          className="text-sm text-zinc-500 hover:underline"
        >
          Log out
        </button>
      </header>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <ul className="grid gap-4 sm:grid-cols-2">
        {templates.map((t) => (
          <li key={t.id} className="space-y-3 rounded-xl border border-zinc-200 p-5 dark:border-zinc-800">
            <div>
              <h2 className="font-semibold">{t.role}</h2>
              <p className="text-sm text-zinc-500">
                {t.interview_type} · {t.max_main_questions} questions
              </p>
            </div>
            <ul className="flex flex-wrap gap-1.5">
              {t.topics.map((topic) => (
                <li key={topic} className="rounded-full bg-zinc-100 px-2 py-0.5 text-xs dark:bg-zinc-800">
                  {topic}
                </li>
              ))}
            </ul>
            <button
              onClick={() => start(t.id)}
              disabled={startingId !== null}
              className="w-full rounded-md bg-zinc-900 px-3 py-2 text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900"
            >
              {startingId === t.id ? "Starting…" : "Start interview"}
            </button>
          </li>
        ))}
      </ul>
    </main>
  );
}
