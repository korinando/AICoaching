"use client";

import { useRouter } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";

import {
  getMe,
  listSessions,
  logout,
  type SessionSummary,
  type User,
} from "./api";

type AppData = {
  user: User | null;
  sessions: SessionSummary[] | null; // null: still loading
  /** Load the interview list again: after starting one, finishing one, or a report arriving. */
  refreshSessions: () => Promise<void>;
};

const AppDataContext = createContext<AppData | null>(null);

/** The account and the interview list, loaded once for every signed-in page. The sidebar and
 * the pages read the same copy, so a new interview shows up everywhere at once. */
export function AppDataProvider({
  ready,
  children,
}: {
  ready: boolean; // true once the login check has passed
  children: React.ReactNode;
}) {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [sessions, setSessions] = useState<SessionSummary[] | null>(null);

  const refreshSessions = useCallback(async () => {
    try {
      setSessions(await listSessions());
    } catch {
      // Keep the list on screen: a failed refresh is usually a short break in the connection.
    }
  }, []);

  useEffect(() => {
    if (!ready) return;
    Promise.all([getMe(), listSessions()])
      .then(([me, list]) => {
        setUser(me);
        setSessions(list);
      })
      .catch(() => {
        // Even the refresh token failed: the login has really expired.
        logout();
        router.replace("/login");
      });
  }, [ready, router]);

  return (
    <AppDataContext value={{ user, sessions, refreshSessions }}>
      {children}
    </AppDataContext>
  );
}

export function useAppData(): AppData {
  const data = useContext(AppDataContext);
  if (!data) throw new Error("useAppData must be used inside AppDataProvider");
  return data;
}
