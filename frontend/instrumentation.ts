// Runs once when the Next.js server starts (Week 7 Step 6). The browser has its own file:
// instrumentation-client.ts.
import * as Sentry from "@sentry/nextjs";

import { sentryOptions } from "./lib/sentry";

export function register() {
  Sentry.init(sentryOptions);
}

// Next.js calls this when rendering a page on the server fails.
export const onRequestError = Sentry.captureRequestError;
