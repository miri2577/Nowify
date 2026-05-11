# Multi-stage build für Coolify-Deployment.
# Stage 1: Vue-SPA bauen (node-sass braucht python+make).
# Stage 2: schlankes Image mit Express-Server der die SPA serviert,
#          /api/track als File-basiertes Now-Playing-Relay implementiert
#          und /wikiart, /wikiart-img als CORS-Proxies durchreicht.

FROM node:20-bookworm AS builder
WORKDIR /app

# node-sass 4.14 (alt) braucht python3+make+g++ für native-build.
RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 make g++ \
    && rm -rf /var/lib/apt/lists/*

COPY package.json yarn.lock ./
RUN npm install --legacy-peer-deps --no-audit --no-fund

COPY . .
ARG VUE_APP_SP_CLIENT_ID=""
ARG VUE_APP_SP_CLIENT_SECRET=""
ENV VUE_APP_SP_CLIENT_ID=${VUE_APP_SP_CLIENT_ID}
ENV VUE_APP_SP_CLIENT_SECRET=${VUE_APP_SP_CLIENT_SECRET}
RUN npm run build && cp -r artframe/webui dist/artframe


FROM node:20-bookworm-slim AS runtime
WORKDIR /app

COPY server/package.json server/package-lock.json* ./
RUN npm install --omit=dev --no-audit --no-fund

COPY server/index.mjs ./index.mjs
COPY --from=builder /app/dist ./public

ENV NODE_ENV=production
ENV PORT=3000
ENV DATA_DIR=/data

VOLUME ["/data"]
EXPOSE 3000

CMD ["node", "index.mjs"]
