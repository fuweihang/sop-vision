FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.29 /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-install-project --no-cache

COPY src ./src
RUN uv sync --locked --no-cache

RUN useradd --create-home --uid 10001 app
USER app

EXPOSE 3001

CMD ["uv", "run", "--no-sync", "uvicorn", "app.main:app", "--app-dir", "src", "--host", "0.0.0.0", "--port", "3001"]
