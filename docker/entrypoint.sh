#!/bin/sh
# Container entrypoint: adopt the host platform's URL/port conventions.
set -e

# Render exposes the service's public URL as RENDER_EXTERNAL_URL; use it for
# rendered-image links and the widget CSP unless explicitly configured.
if [ -z "${ASTROLENS_PUBLIC_BASE_URL:-}" ] && [ -n "${RENDER_EXTERNAL_URL:-}" ]; then
    export ASTROLENS_PUBLIC_BASE_URL="$RENDER_EXTERNAL_URL"
fi

exec uvicorn astrolens.api.main:app --host 0.0.0.0 --port "${PORT:-8000}"
