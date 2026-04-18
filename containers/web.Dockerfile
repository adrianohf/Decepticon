FROM node:24-slim AS base

WORKDIR /app

# Install dependencies
FROM base AS deps
# openssl is required by Prisma's migration engine binary
RUN apt-get update -y && apt-get install -y openssl && rm -rf /var/lib/apt/lists/*
COPY package.json package-lock.json ./
COPY clients/cli/package.json clients/cli/
COPY clients/web/package.json clients/web/
COPY clients/shared/streaming/package.json clients/shared/streaming/
RUN npm ci

# Generate Prisma client
COPY clients/web/prisma ./clients/web/prisma
COPY clients/web/prisma.config.ts ./clients/web/prisma.config.ts
WORKDIR /app/clients/web
RUN npx prisma generate
WORKDIR /app

# Build application
FROM base AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY package.json package-lock.json ./
COPY clients/shared/ clients/shared/
COPY clients/web/ clients/web/
# Prisma generates to src/generated/ (gitignored) — carry it over from deps stage
COPY --from=deps /app/clients/web/src/generated ./clients/web/src/generated
WORKDIR /app/clients/web
# Explicit OSS edition — proxy.ts + hasEE() check this env var.
# EE builds override via --build-arg or separate Dockerfile.
ENV NEXT_PUBLIC_DECEPTICON_EDITION=oss
# Turbopack aliases @prisma/client as @prisma/client-<schema-hash> in server chunks
# (external module, not bundled). Copy @prisma/client under that alias so the
# standalone server can resolve it at runtime. Hash is extracted from build output.
RUN npm run build && \
    # Turbopack aliases external packages as <name>-<16hexchars> in server chunks.
    # Standalone build omits these aliases. Find every alias, derive the original
    # package name, and copy it into standalone/node_modules under the alias.
    grep -roh '"[^"]*-[a-f0-9]\{16\}[^"]*"' .next/server/chunks/ 2>/dev/null \
        | tr -d '"' \
        | grep -oE '^(@[^/]+/[^/]+-[a-f0-9]{16,}|[^@/][^/]+-[a-f0-9]{16,})' \
        | sort -u \
        | while read alias; do \
            pkg=$(echo "$alias" | sed -E 's/-[a-f0-9]{16,}$//'); \
            dst=".next/standalone/node_modules/$alias"; \
            [ -d "$dst" ] && continue; \
            for base in ".next/standalone/node_modules" "../../node_modules"; do \
                if [ -d "$base/$pkg" ]; then \
                    echo "Turbopack alias: $alias <- $pkg"; \
                    cp -r "$base/$pkg/." "$dst/"; \
                    break; \
                fi; \
            done; \
        done

# Production image
FROM base AS runner
WORKDIR /app

ENV NODE_ENV=production
# OSS mode — same edition marker used at build time, propagated to runtime.
ENV NEXT_PUBLIC_DECEPTICON_EDITION=oss

# openssl required by Prisma migration engine
RUN apt-get update -y && apt-get install -y openssl && rm -rf /var/lib/apt/lists/*

RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

COPY --from=builder /app/clients/web/public ./public
# Next.js 16 standalone nests under the original path (clients/web/)
COPY --from=builder --chown=nextjs:nodejs /app/clients/web/.next/standalone/clients/web ./
COPY --from=builder --chown=nextjs:nodejs /app/clients/web/.next/standalone/node_modules ./node_modules
COPY --from=builder --chown=nextjs:nodejs /app/clients/web/.next/static ./.next/static

# Prisma CLI for migrations — fresh install brings the full transitive dep tree.
# Cherry-picking individual packages breaks on deep deps (effect, @prisma/debug, etc.).
# Pin to the exact version from deps stage to guarantee schema/engine compatibility.
COPY --from=deps /app/node_modules/prisma/package.json /tmp/prisma-version.json
COPY --from=deps /app/node_modules/dotenv/package.json /tmp/dotenv-version.json
RUN PRISMA_VER=$(node -p "require('/tmp/prisma-version.json').version") && \
    DOTENV_VER=$(node -p "require('/tmp/dotenv-version.json').version") && \
    npm install --no-save --prefix /tmp/prisma-cli \
        "prisma@${PRISMA_VER}" "dotenv@${DOTENV_VER}" && \
    cp -rn /tmp/prisma-cli/node_modules/. ./node_modules/ && \
    rm -rf /tmp/prisma-cli /tmp/prisma-version.json /tmp/dotenv-version.json
COPY --from=deps --chown=nextjs:nodejs /app/clients/web/prisma ./prisma
COPY --chown=nextjs:nodejs clients/web/prisma.config.ts ./prisma.config.ts

# Startup entrypoint: run DB migrations then start Next.js server
COPY containers/web-entrypoint.sh ./entrypoint.sh
RUN chmod +x ./entrypoint.sh

USER nextjs

EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

CMD ["./entrypoint.sh"]
