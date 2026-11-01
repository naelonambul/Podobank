FROM python:3.15.2-slim
COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY backend ./backend

RUN uv sync --locked --no-dev --no-editable

ENV PATH="/app/.venv/bin:$PATH"

USER 10001:10001

EXPOSE 8000

CMD ["uvicorn", "podobank_api.app:app", "--host", "0.0.0.0", "--port", "8000"]
