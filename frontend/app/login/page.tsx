"use client";

import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";

import { Logo } from "@/components/icons";
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
      router.push("/");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
      setBusy(false);
    }
  }

  const isRegister = mode === "register";

  return (
    <main className="flex flex-1 flex-col items-center justify-center gap-6 p-4">
      <div className="flex flex-col items-center gap-3 text-center">
        <Logo className="h-11 w-11" />
        <div>
          <p className="text-2xl font-semibold tracking-tight">Offerward</p>
          <p className="text-sm text-muted">
            Practise job interviews out loud, with feedback
          </p>
        </div>
      </div>
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm space-y-4 rounded-2xl border border-line bg-surface p-6 shadow-sm"
      >
        <h1 className="text-lg font-semibold">
          {isRegister ? "Create an account" : "Log in"}
        </h1>

        {isRegister && (
          <Field label="Name">
            <input
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              className={inputClass}
            />
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

        {error && (
          <p role="alert" className="text-sm text-danger">
            {error}
          </p>
        )}

        <button type="submit" disabled={busy} className={buttonClass}>
          {busy ? "Please wait…" : isRegister ? "Create account" : "Log in"}
        </button>

        <button
          type="button"
          onClick={() => {
            setMode(isRegister ? "login" : "register");
            setError(null);
          }}
          className="w-full text-sm text-muted hover:text-foreground hover:underline"
        >
          {isRegister
            ? "Already have an account? Log in"
            : "No account yet? Create one"}
        </button>
      </form>
    </main>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block space-y-1">
      <span className="text-sm font-medium">{label}</span>
      {children}
    </label>
  );
}

const inputClass =
  "w-full rounded-lg border border-line bg-transparent px-3 py-2 outline-none focus:border-accent focus:ring-2 focus:ring-accent/20";
const buttonClass =
  "w-full rounded-lg bg-accent px-3 py-2.5 font-medium text-accent-fg hover:bg-accent-hover disabled:opacity-50";
