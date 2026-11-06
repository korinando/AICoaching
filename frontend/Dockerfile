# The Next.js frontend (Week 7 Step 1). The plan hosts it on Vercel, which builds it itself; this
# image runs the whole app in Docker, and keeps the option of hosting it anywhere.
#
# Three stages: install, build, run. Only the last one is kept, and it holds Next's "standalone"
# output: the server and just the files it uses, without node_modules or the source code.

# ---- Stage 1: install packages, exactly as package-lock.json says ----------------------------------
FROM node:24-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

# ---- Stage 2: build -------------------------------------------------------------------------------
FROM node:24-alpine AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# NEXT_PUBLIC_ values are written into the browser's JavaScript during the build, not read when it
# runs. So the API address is a build argument: each environment needs its own build.
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# ---- Stage 3: run ---------------------------------------------------------------------------------
FROM node:24-alpine
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0

# The standalone server doesn't include static files and public/ (a CDN usually serves them), so
# they're copied next to it, where server.js serves them itself. "node" is a non-root user that comes
# with the image.
COPY --from=build --chown=node:node /app/.next/standalone ./
COPY --from=build --chown=node:node /app/.next/static ./.next/static
COPY --from=build --chown=node:node /app/public ./public

USER node
EXPOSE 3000
CMD ["node", "server.js"]
