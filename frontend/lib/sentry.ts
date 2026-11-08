// The same Sentry settings in the browser and on the Next.js server (Week 7 Step 6).
// A DSN only lets you *send* errors to one Sentry project, not read them, so it's safe in the
// browser's code: that's why it's a NEXT_PUBLIC_ variable. Without it (development), nothing is sent.
export const sentryOptions = {
  dsn: process.env.NEXT_PUBLIC_SENTRY_DSN,
  enabled: Boolean(process.env.NEXT_PUBLIC_SENTRY_DSN),
  // No IP addresses, cookies or request headers.
  sendDefaultPii: false,
  // Errors only. Performance tracing would use up the free plan's quota for little gain.
  tracesSampleRate: 0,
};
