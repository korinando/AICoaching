"use client";

import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";

import { login, register } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault(); // stop the browser's own form submit (a full page reload)
    setError(null);
    setBusy(true);
    try {
      if (mode === "login") await login(email, password);
      else await register(email, password, name);
      router.push("/dashboard");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
      setBusy(false);
    }
  }

  const isRegister = mode === "register";

  return (
    <main className="flex flex-1 items-center justify-center p-4">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm space-y-4 rounded-xl border border-zinc-200 p-6 shadow-sm dark:border-zinc-800"
      >
        <h1 className="text-xl font-semibold">{isRegister ? "Create an account" : "Log in"}</h1>

        {isRegister && (
          <Field label="Name">
            <input required value={name} onChange={(e) => setName(e.target.value)} className={inputClass} />
          </Field>
        )}
        <Field label="Email">
          <input
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className={inputClass}
          />
        </Field>
        <Field label="Password">
          <input
            type="password"
            required
            minLength={isRegister ? 8 : undefined}
            autoComplete={isRegister ? "new-password" : "current-password"}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className={inputClass}
          />
        </Field>

        {error && <p className="text-sm text-red-600">{error}</p>}

        <button type="submit" disabled={busy} className={buttonClass}>
          {busy ? "Please wait…" : isRegister ? "Create account" : "Log in"}
        </button>

        <button
          type="button"
          onClick={() => {
            setMode(isRegister ? "login" : "register");
            setError(null);
          }}
          className="w-full text-sm text-zinc-500 hover:underline"
        >
          {isRegister ? "Already have an account? Log in" : "No account yet? Create one"}
        </button>
      </form>
    </main>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block space-y-1">
      <span className="text-sm font-medium">{label}</span>
      {children}
    </label>
  );
}

const inputClass =
  "w-full rounded-md border border-zinc-300 bg-transparent px-3 py-2 outline-none focus:border-zinc-500 dark:border-zinc-700";
const buttonClass =
  "w-full rounded-md bg-zinc-900 px-3 py-2 font-medium text-white hover:bg-zinc-700 disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900";
