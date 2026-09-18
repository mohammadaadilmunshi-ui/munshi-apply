FROM node:22-bookworm-slim AS runtime-builder

WORKDIR /src
COPY . .
RUN npm ci
RUN node scripts/build-plan-runtime.mjs

FROM python:3.12-slim-bookworm

ARG MUNSHI_APPLY_COMMIT_SHA=unknown

LABEL org.opencontainers.image.title="MUNSHI Apply Production"
LABEL org.opencontainers.image.revision="${MUNSHI_APPLY_COMMIT_SHA}"

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        chromium \
        git \
        fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .
COPY --from=runtime-builder /src/apps/native-host/browser-dist/plan-runtime.js /app/apps/native-host/browser-dist/plan-runtime.js

RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -e './apps/native-host[dev]'

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin munshiapply \
    && mkdir -p /data \
    && chown -R munshiapply:munshiapply /data /app

USER munshiapply

ENV MUNSHI_RUNTIME_ROOT=/data
ENV MUNSHI_DATABASE_PATH=/data/munshi-apply.sqlite
ENV MUNSHI_MIGRATIONS_PATH=/app/migrations
ENV MUNSHI_BROWSER_EXECUTABLE=/usr/bin/chromium
ENV MUNSHI_ENVIRONMENT=production

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "munshi_apply_native.main:app", "--host", "0.0.0.0", "--port", "8000"]
