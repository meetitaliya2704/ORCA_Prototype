FROM node:20-alpine AS base

# Stage 1: Install dependencies only when needed
FROM base AS deps
RUN apk add --no-cache libc6-compat
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

# Stage 2: Rebuild the source code only when needed
FROM base AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Environment variables must be present at build time for Next.js to bake them into client bundles
ARG NEXT_PUBLIC_ORCA_API_BASE_URL=http://localhost:8000
ARG NEXT_PUBLIC_MAP_STYLE_URL=https://tiles.openfreemap.org/styles/liberty
ARG NEXT_PUBLIC_ORCA_ASSISTANT_MODE=live
ARG NEXT_PUBLIC_ORCA_DEMO_MODE=false
ARG NEXT_PUBLIC_ORCA_PRESENTATION_MODE=false
ARG NEXT_PUBLIC_ORCA_REQUEST_TIMEOUT_MS=90000
ARG NEXT_PUBLIC_ORCA_DEV_DIAGNOSTICS=false

ENV NEXT_PUBLIC_ORCA_API_BASE_URL=$NEXT_PUBLIC_ORCA_API_BASE_URL
ENV NEXT_PUBLIC_MAP_STYLE_URL=$NEXT_PUBLIC_MAP_STYLE_URL
ENV NEXT_PUBLIC_ORCA_ASSISTANT_MODE=$NEXT_PUBLIC_ORCA_ASSISTANT_MODE
ENV NEXT_PUBLIC_ORCA_DEMO_MODE=$NEXT_PUBLIC_ORCA_DEMO_MODE
ENV NEXT_PUBLIC_ORCA_PRESENTATION_MODE=$NEXT_PUBLIC_ORCA_PRESENTATION_MODE
ENV NEXT_PUBLIC_ORCA_REQUEST_TIMEOUT_MS=$NEXT_PUBLIC_ORCA_REQUEST_TIMEOUT_MS
ENV NEXT_PUBLIC_ORCA_DEV_DIAGNOSTICS=$NEXT_PUBLIC_ORCA_DEV_DIAGNOSTICS
ENV NEXT_TELEMETRY_DISABLED=1

RUN npm run build

# Stage 3: Production runner
FROM base AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

COPY --from=builder /app/public ./public
COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/.next ./.next

USER nextjs

EXPOSE 3000

CMD ["npm", "start"]

