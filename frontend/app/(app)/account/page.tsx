"use client";

import { useRouter } from "next/navigation";

import { Avatar } from "@/components/Avatar";
import { LogoutIcon } from "@/components/icons";
import { logout } from "@/lib/api";
import { useAppData } from "@/lib/appData";

/** Your account: who you are, how much you've practised, and (coming next) your CV. */
export default function AccountPage() {
  const router = useRouter();
  const { user, sessions } = useAppData();

  const finished = (sessions ?? []).filter((s) => s.status !== "in_progress");
  const scored = (sessions ?? []).filter((s) => s.overall_score !== null);

  return (
    <main className="mx-auto w-full max-w-3xl space-y-6 px-4 py-8 md:px-8 md:py-12">
      <h1 className="text-3xl font-semibold tracking-tight">Account</h1>

      <section className="flex items-center gap-4 rounded-2xl border border-line bg-surface p-5">
        <Avatar name={user?.name} size="lg" />
        <div className="min-w-0">
          <p className="truncate text-lg font-semibold">{user?.name ?? " "}</p>
          <p className="truncate text-sm text-muted">{user?.email ?? " "}</p>
          {user && (
            <p className="mt-1 text-xs text-muted">
              Member since{" "}
              {new Date(user.created_at).toLocaleDateString(undefined, {
                year: "numeric",
                month: "long",
                day: "numeric",
              })}
            </p>
          )}
        </div>
      </section>

      <section
        aria-labelledby="practice"
        className="rounded-2xl border border-line bg-surface p-5"
      >
        <h2 id="practice" className="mb-3 font-semibold">
          Your practice
        </h2>
        <dl className="grid grid-cols-3 gap-3 text-center">
          <Figure
            label="Interviews"
            value={sessions ? finished.length : null}
          />
          <Figure
            label="With a report"
            value={sessions ? scored.length : null}
          />
          <Figure
            label="Average score"
            value={
              scored.length
                ? (
                    scored.reduce((sum, s) => sum + (s.overall_score ?? 0), 0) /
                    scored.length
                  ).toFixed(1)
                : sessions
                  ? "–"
                  : null
            }
          />
        </dl>
      </section>

      <section
        aria-labelledby="cv"
        className="space-y-4 rounded-2xl border border-line bg-surface p-5"
      >
        <div className="flex flex-wrap items-center gap-2">
          <h2 id="cv" className="font-semibold">
            Your CV
          </h2>
          <span className="rounded-md bg-accent-soft px-1.5 py-0.5 text-xs font-medium text-accent">
            Coming soon
          </span>
        </div>
        <p className="text-sm text-muted">
          Add your CV and Offerward will suggest interviews for the roles and
          skills on it, and ask about the projects you&apos;ve actually done.
        </p>
        {/* A placeholder, not a button: nothing can be uploaded yet, so nothing pretends to. */}
        <div
          aria-disabled
          className="flex flex-col items-center gap-1 rounded-xl border border-dashed border-line px-4 py-8 text-center"
        >
          <p className="text-sm font-medium text-muted">CV upload</p>
          <p className="text-xs text-muted">Not available yet</p>
        </div>
      </section>

      <section className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-line bg-surface p-5">
        <div>
          <h2 className="font-semibold">Log out</h2>
          <p className="text-sm text-muted">
            Your interviews and reports stay saved.
          </p>
        </div>
        <button
          type="button"
          onClick={() => {
            logout();
            router.replace("/login");
          }}
          className="flex items-center gap-1.5 rounded-lg border border-line px-3 py-1.5 text-sm hover:border-danger hover:text-danger"
        >
          <LogoutIcon className="h-4 w-4" />
          Log out
        </button>
      </section>
    </main>
  );
}

function Figure({
  label,
  value,
}: {
  label: string;
  value: number | string | null; // null: still loading
}) {
  return (
    <div className="rounded-xl bg-surface-2 p-3">
      <dt className="text-xs text-muted">{label}</dt>
      <dd className="mt-1 text-2xl font-semibold">
        {value ?? (
          <span className="inline-block h-6 w-8 animate-pulse rounded bg-surface-3" />
        )}
      </dd>
    </div>
  );
}
