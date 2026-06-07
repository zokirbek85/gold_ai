FROM node:20-alpine AS builder

WORKDIR /app

# Accept BACKEND_URL at build time so next.config.ts rewrites are correct
ARG BACKEND_URL=http://backend:8001
ENV BACKEND_URL=$BACKEND_URL

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM node:20-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production
# Also set at runtime so the standalone server can re-evaluate if needed
ENV BACKEND_URL=http://backend:8001

COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

EXPOSE 3000

CMD ["node", "server.js"]
