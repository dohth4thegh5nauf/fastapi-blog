# Build a minimal runtime environment from the committed uv lockfile.
FROM ghcr.io/astral-sh/uv:0.13.7 AS uv
FROM python:3.15.0-slim-bookworm AS builder

COPY --from=uv /uv /uvx /bin/
WORKDIR /app

COPY pyproject.toml uv.lock README.md LICENSE.md ./
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable

# Keep the runtime image free of compilers, uv and development dependencies.
FROM python:3.15.0-slim-bookworm AS runtime

RUN apt-get update \
    && apt-get install -y --only-upgrade --no-install-recommends \
      apt libapt-pkg6.0 openssl libssl3 \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --chown=10001:10001 tests/examples/compose_demo.py ./compose_demo.py
COPY --chown=10001:10001 tests/examples/posts ./posts
COPY --chown=10001:10001 tests/examples/pages ./pages

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import sys,urllib.request;sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health/ready',timeout=4).status==200 else 1)"

USER 10001:10001
CMD ["uvicorn", "compose_demo:app", "--host", "0.0.0.0", "--port", "8000"]
