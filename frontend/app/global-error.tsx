"use client"; // error boundaries must be Client Components

import * as Sentry from "@sentry/nextjs";
import { useEffect } from "react";

// The last line of defence: shown instead of the whole app when even the root layout crashes.
// React has caught the error here, so it never reaches the browser's "uncaught error" handler:
// it must be sent to Sentry by hand (Week 7 Step 6).
export default function GlobalError({
  error,
  retry,
}: {
  error: unknown;
  retry: () => void;
}) {
  useEffect(() => {
    Sentry.captureException(error);
  }, [error]);

  // It replaces the root layout, so it brings its own <html> and <body>, and no global styles.
  return (
    <html lang="en">
      <body style={{ fontFamily: "system-ui, sans-serif", padding: "2rem" }}>
        <title>Offerward</title>
        <h1>Something went wrong.</h1>
        <p>The error has been reported. Please try again.</p>
        <button onClick={() => retry()}>Try again</button>
      </body>
    </html>
  );
}
