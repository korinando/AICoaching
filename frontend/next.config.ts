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

export default nextConfig;
