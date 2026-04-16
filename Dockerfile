FROM python:3.12-slim AS base

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

# Install dependencies first (cached layer)
ARG GITHUB_TOKEN
COPY pyproject.toml uv.lock ./
RUN git config --global url."https://${GITHUB_TOKEN}@github.com/".insteadOf "https://github.com/" && \
    uv sync --frozen --no-dev && \
    git config --global --unset-all url."https://${GITHUB_TOKEN}@github.com/".insteadOf

# Copy application code
COPY src/ ./src/

EXPOSE 8001

CMD ["uv", "run", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8001"]
