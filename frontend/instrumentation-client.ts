// Runs in the browser before the app becomes interactive: from then on, an error nobody catches
// is sent to Sentry (Week 7 Step 6).
import * as Sentry from "@sentry/nextjs";

import { sentryOptions } from "./lib/sentry";

Sentry.init(sentryOptions);

// Lets Sentry know when the page changes, so an error shows which page it happened on.
export const onRouterTransitionStart = Sentry.captureRouterTransitionStart;
