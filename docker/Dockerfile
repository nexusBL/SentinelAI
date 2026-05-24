FROM mcr.microsoft.com/playwright/python:v1.58.0-noble

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements-docker.txt /app/requirements-docker.txt

RUN pip install --no-cache-dir -r requirements-docker.txt

COPY --chown=pwuser:pwuser . /app

RUN mkdir -p /app/artifacts/runs /app/memory_store /app/auth_store \
    && chown -R pwuser:pwuser /app \
    && chmod +x /app/docker/entrypoint.sh

USER root

EXPOSE 8000

ENTRYPOINT ["/app/docker/entrypoint.sh"]

CMD ["gunicorn", "dashboard.app:app", "--worker-class", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000", "--workers", "1", "--timeout", "120", "--access-logfile", "-", "--error-logfile", "-"]
