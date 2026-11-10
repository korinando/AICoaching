"use client";

import Link from "next/link";
import { Suspense, useState } from "react";

import { DebugButton } from "@/components/DebugButton";
import { Logo, MenuIcon } from "@/components/icons";
import { NewInterviewProvider } from "@/components/NewInterview";
import { Sidebar } from "@/components/Sidebar";
import { AppDataProvider } from "@/lib/appData";
import { useRequireLogin } from "@/lib/useRequireLogin";

/** Every signed-in page: the interview list on the left, the page on the right.
 * "(app)" is a route group: the brackets keep it out of the URL, so this folder's page.tsx is the home page, "/". */
export default function AppLayout({ children }: { children: React.ReactNode }) {
  const ready = useRequireLogin();
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <AppDataProvider ready={ready}>
      <NewInterviewProvider>
        <div className="flex h-dvh overflow-hidden">
          {/* Suspense: the sidebar reads the URL to highlight the open interview. */}
          <Suspense
            fallback={
              <aside className="hidden w-72 border-r border-line bg-surface-2 md:block" />
            }
          >
            <Sidebar open={menuOpen} onClose={() => setMenuOpen(false)} />
          </Suspense>

          <div className="flex min-w-0 flex-1 flex-col">
            <header className="flex items-center gap-2 border-b border-line px-3 py-2 md:hidden">
              <button
                type="button"
                onClick={() => setMenuOpen(true)}
                aria-label="Open menu"
                className="rounded-md p-1.5 text-muted hover:bg-surface-3"
              >
                <MenuIcon />
              </button>
              <Link
                href="/"
                className="flex items-center gap-2 font-semibold tracking-tight"
              >
                <Logo className="h-6 w-6" />
                Offerward
              </Link>
            </header>
            <div className="flex-1 overflow-y-auto">{children}</div>
          </div>
        </div>
        {/* Admins only. Suspense: the panel reads the URL to find the open interview. */}
        <Suspense fallback={null}>
          <DebugButton />
        </Suspense>
      </NewInterviewProvider>
    </AppDataProvider>
  );
}
