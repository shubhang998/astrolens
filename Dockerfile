FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.7 /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

# Install locked dependencies first so source edits do not invalidate this layer.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-install-project --no-dev

COPY src ./src
RUN uv sync --frozen --no-dev

RUN useradd --create-home --uid 1000 astrolens \
    && mkdir -p /app/.astrolens-cache \
    && chown -R astrolens:astrolens /app/.astrolens-cache
USER astrolens

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/v1/health', timeout=4)" || exit 1

CMD ["uvicorn", "astrolens.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
