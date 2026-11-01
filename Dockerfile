FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY backend ./backend

RUN python -m pip install --no-cache-dir .

USER 10001:10001

EXPOSE 8000

CMD ["sh", "-c", "podobank-api init-db && uvicorn podobank_api.app:app --host 0.0.0.0 --port 8000"]
