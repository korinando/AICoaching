"use client";

import { useRouter } from "next/navigation";
import { useEffect, useSyncExternalStore } from "react";

import { isLoggedIn } from "./api";

// "storage" fires when another tab changes localStorage (e.g. logs out there).
function subscribe(onChange: () => void) {
  window.addEventListener("storage", onChange);
  return () => window.removeEventListener("storage", onChange);
}

/** Sends the visitor to /login if there's no saved login. Returns true once it's safe to
 * load data.
 *
 * useSyncExternalStore is React's tool for reading a value that lives outside React, like
 * localStorage. The third function is the answer during server rendering, where there is no
 * localStorage: null = "don't know yet", so nothing is loaded and nobody is redirected. */
export function useRequireLogin(): boolean {
  const router = useRouter();
  const loggedIn = useSyncExternalStore(subscribe, isLoggedIn, () => null);

  useEffect(() => {
    if (loggedIn === false) router.replace("/login");
  }, [loggedIn, router]);

  return loggedIn === true;
}
