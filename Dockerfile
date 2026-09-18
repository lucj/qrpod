FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

COPY app/pyproject.toml app/uv.lock ./
RUN uv sync --frozen --no-dev

COPY app/ ./

RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

USER appuser

EXPOSE 5000

ENV FLASK_APP=main:app
ENV FLASK_ENV=production

CMD ["uv", "run", "gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "main:app"]
