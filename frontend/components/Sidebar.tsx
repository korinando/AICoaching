"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import { logout, type SessionSummary } from "@/lib/api";
import { useAppData } from "@/lib/appData";

import { Avatar } from "./Avatar";
import { CloseIcon, Logo, LogoutIcon, PlusIcon } from "./icons";
import { useOpenNewInterview } from "./NewInterview";

/** Past interviews, newest first, like a chat app's conversation list. On a phone it slides in
 * over the page; on a wider screen it's always there. */
export function Sidebar({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const { user, sessions } = useAppData();
  const pathname = usePathname();
  const router = useRouter();
  const openNewInterview = useOpenNewInterview();

  return (
    <>
      {/* The dimmed page behind the menu on a phone; a tap closes it. */}
      <div
        onClick={onClose}
        aria-hidden
        className={`fixed inset-0 z-30 bg-black/40 transition-opacity md:hidden ${
          open ? "opacity-100" : "pointer-events-none opacity-0"
        }`}
      />
      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-72 flex-col border-r border-line bg-surface-2 transition-transform md:static md:translate-x-0 ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex items-center justify-between px-4 pb-2 pt-4">
          <Link
            href="/"
            onClick={onClose}
            className="flex items-center gap-2 font-semibold tracking-tight"
          >
            <Logo />
            Offerward
          </Link>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close menu"
            className="rounded-md p-1.5 text-muted hover:bg-surface-3 md:hidden"
          >
            <CloseIcon />
          </button>
        </div>

        <div className="space-y-1 px-3 py-2">
          <button
            type="button"
            onClick={() => {
              onClose();
              openNewInterview();
            }}
            className="flex w-full items-center gap-2 rounded-lg border border-line bg-surface px-3 py-2 text-sm font-medium shadow-sm hover:bg-surface-3"
          >
            <PlusIcon className="h-4 w-4" />
            New interview
          </button>
        </div>

        <nav
          aria-label="Past interviews"
          className="flex-1 overflow-y-auto px-3 pb-4"
        >
          {sessions === null ? (
            <SkeletonList />
          ) : sessions.length === 0 ? (
            <p className="px-2 pt-4 text-sm text-muted">
              Your interviews will appear here.
            </p>
          ) : (
            groupByDay(sessions).map(([label, group]) => (
              <section key={label} className="pt-4">
                <h2 className="px-2 pb-1 text-xs font-medium text-muted">
                  {label}
                </h2>
                <ul className="space-y-0.5">
                  {group.map((session) => (
                    <li key={session.id}>
                      <SessionLink
                        session={session}
                        active={pathname.startsWith(`/interview/${session.id}`)}
                        onClick={onClose}
                      />
                    </li>
                  ))}
                </ul>
              </section>
            ))
          )}
        </nav>

        <div className="flex items-center gap-1 border-t border-line px-2 py-2">
          {/* The account page: profile now, and later the CV that interviews can be built on. */}
          <Link
            href="/account"
            onClick={onClose}
            aria-current={pathname === "/account" ? "page" : undefined}
            title="Your account"
            className={`flex min-w-0 flex-1 items-center gap-3 rounded-lg px-2 py-1.5 ${
              pathname === "/account" ? "bg-surface-3" : "hover:bg-surface-3"
            }`}
          >
            <Avatar name={user?.name} />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium">
                {user?.name ?? " "}
              </span>
              <span className="block truncate text-xs text-muted">
                {user?.email ?? " "}
              </span>
            </span>
          </Link>
          <button
            type="button"
            onClick={() => {
              logout();
              router.replace("/login");
            }}
            aria-label="Log out"
            title="Log out"
            className="rounded-md p-1.5 text-muted hover:bg-surface-3 hover:text-foreground"
          >
            <LogoutIcon className="h-4 w-4" />
          </button>
        </div>
      </aside>
    </>
  );
}

function SessionLink({
  session,
  active,
  onClick,
}: {
  session: SessionSummary;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <Link
      href={`/interview/${session.id}`}
      onClick={onClick}
      aria-current={active ? "page" : undefined}
      className={`flex items-center justify-between gap-2 rounded-lg px-2 py-2 text-sm ${
        active ? "bg-surface-3 font-medium" : "hover:bg-surface-3"
      }`}
    >
      <span className="truncate">{session.role}</span>
      <Badge session={session} />
    </Link>
  );
}

function Badge({ session }: { session: SessionSummary }) {
  if (session.overall_score !== null) {
    return (
      <span className="shrink-0 rounded-md bg-surface px-1.5 py-0.5 text-xs font-medium tabular-nums text-foreground ring-1 ring-line">
        {session.overall_score.toFixed(1)}
      </span>
    );
  }
  if (session.status === "in_progress") {
    return (
      <span className="flex shrink-0 items-center gap-1 text-xs text-accent">
        <span className="h-1.5 w-1.5 rounded-full bg-accent" />
        Live
      </span>
    );
  }
  if (session.report_status === "pending") {
    return <span className="shrink-0 text-xs text-muted">Scoring…</span>;
  }
  return null;
}

function SkeletonList() {
  return (
    <div className="space-y-2 pt-4" aria-label="Loading interviews">
      {[0, 1, 2, 3].map((i) => (
        <div key={i} className="h-8 animate-pulse rounded-lg bg-surface-3" />
      ))}
    </div>
  );
}

/** Today, Yesterday, Previous 7 days, then one group per month: like a chat app's history. */
function groupByDay(sessions: SessionSummary[]): [string, SessionSummary[]][] {
  const startOfToday = new Date();
  startOfToday.setHours(0, 0, 0, 0);
  const day = 24 * 60 * 60 * 1000;
  const groups = new Map<string, SessionSummary[]>();
  const newestFirst = [...sessions].sort(
    (a, b) => Date.parse(b.started_at) - Date.parse(a.started_at),
  );
  for (const session of newestFirst) {
    const started = new Date(session.started_at);
    const age = startOfToday.getTime() - started.getTime();
    const label =
      age <= 0
        ? "Today"
        : age <= day
          ? "Yesterday"
          : age <= 7 * day
            ? "Previous 7 days"
            : started.toLocaleDateString(undefined, {
                month: "long",
                year: "numeric",
              });
    groups.set(label, [...(groups.get(label) ?? []), session]);
  }
  return [...groups];
}
