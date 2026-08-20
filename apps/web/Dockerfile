# ============================================================
# TradeDNA Web Production Multi-Stage Dockerfile
# ============================================================

# Stage 1: Install Dependencies
FROM node:20-alpine AS deps
RUN apk add --no-cache libc6-compat
WORKDIR /app

COPY package*.json ./
RUN npm ci

# Stage 2: Build Application
FROM node:20-alpine AS builder
WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY . .

ENV NEXT_TELEMETRY_DISABLED=1
ENV NODE_ENV=production

RUN npm run build

# Stage 3: Production Minimal Runner
FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

# Use non-root node user provided by alpine
USER node

COPY --from=builder --chown=node:node /app/package*.json ./
COPY --from=builder --chown=node:node /app/.next ./.next
COPY --from=builder --chown=node:node /app/node_modules ./node_modules

EXPOSE 3000

# Healthcheck
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:3000/ || exit 1

STOPSIGNAL SIGTERM

CMD ["npm", "start"]
