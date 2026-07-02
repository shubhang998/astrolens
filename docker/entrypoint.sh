#!/bin/sh
# Container entrypoint: adopt the host platform's URL/port conventions.
set -e

# Render exposes the service's public URL as RENDER_EXTERNAL_URL; use it for
# rendered-image links and the widget CSP unless explicitly configured.
if [ -z "${ASTROLENS_PUBLIC_BASE_URL:-}" ] && [ -n "${RENDER_EXTERNAL_URL:-}" ]; then
    export ASTROLENS_PUBLIC_BASE_URL="$RENDER_EXTERNAL_URL"
fi

# Persistent render cache: platform disks can be mounted root-owned while the
# app runs unprivileged; fall back to the local ephemeral cache rather than
# failing every render.
if [ -n "${ASTROLENS_RENDER_CACHE_DIR:-}" ]; then
    mkdir -p "$ASTROLENS_RENDER_CACHE_DIR" 2>/dev/null || true
    if [ ! -w "$ASTROLENS_RENDER_CACHE_DIR" ]; then
        echo "warn: $ASTROLENS_RENDER_CACHE_DIR is not writable; using local cache" >&2
        unset ASTROLENS_RENDER_CACHE_DIR
    fi
fi

exec uvicorn astrolens.api.main:app --host 0.0.0.0 --port "${PORT:-8000}"
