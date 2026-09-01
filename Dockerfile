FROM python:3.14-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

COPY pyproject.toml ./
COPY app ./app

RUN python -m pip wheel --wheel-dir /wheels .

FROM python:3.14-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN groupadd --gid 10001 devflow \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin devflow

WORKDIR /app

COPY --from=builder /wheels /wheels
RUN python -m pip install --no-cache-dir --no-index --find-links=/wheels devflow \
    && rm -rf /wheels

COPY --chown=10001:10001 alembic.ini ./
COPY --chown=10001:10001 alembic ./alembic
COPY --chown=10001:10001 app ./app

USER 10001:10001

EXPOSE 8000

HEALTHCHECK --interval=5s --timeout=3s --start-period=10s --retries=12 \
  CMD ["python", "-c", "from urllib.request import urlopen; urlopen('http://127.0.0.1:8000/healthz', timeout=2).read()"]

CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
