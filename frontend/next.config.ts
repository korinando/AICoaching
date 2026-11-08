import { withSentryConfig } from "@sentry/nextjs/config";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The build also writes .next/standalone: a small server with only the files it uses, for the
  // Docker image (Week 7). `npm run dev` and `npm start` are unchanged.
  output: "standalone",
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default withSentryConfig(nextConfig, {
  // Brave and ad blockers block requests to sentry.io. Sent to /monitoring on this site
  // instead, the Next.js server passes them on, so errors from those browsers still arrive.
  tunnelRoute: "/monitoring",
  // Readable stack traces: the build uploads its source maps to Sentry, then deletes them so
  // visitors can't download the original code. Only when these are set (on Vercel); without
  // them, the build skips the upload and works as before.
  org: process.env.SENTRY_ORG,
  project: process.env.SENTRY_PROJECT,
  authToken: process.env.SENTRY_AUTH_TOKEN,
  sourcemaps: { disable: !process.env.SENTRY_AUTH_TOKEN },
  silent: !process.env.CI,
  telemetry: false, // don't send Sentry data about my builds
});
