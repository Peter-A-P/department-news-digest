# One image for both halves of the deployment (PLAN.md section 2.5):
#
#   the Cloud Run job      clippings run              daily, from Cloud Scheduler
#   the Cloud Run service  clippings serve            the read-only pages
#
# Built from the repository root: docker build -f deploy/Dockerfile .
#
# The embedding model is downloaded at build time and baked in, so a daily run does not
# fetch 130 MB from a model hub before it starts and cannot fail because the hub is down.

FROM python:3.13-slim AS build

COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app

# git, because the gateway is installed from its tagged repository.
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --extra embed --extra gcs --no-install-project
COPY clippings ./clippings
COPY docs/sources.md ./docs/sources.md
RUN uv sync --frozen --no-dev --extra embed --extra gcs

ENV FASTEMBED_CACHE_PATH=/app/models
RUN /app/.venv/bin/python -c "from clippings.cluster.embed import FastEmbed; FastEmbed().embed(['warm'])"
# Readable by the unprivileged user the containers run as, whatever the permissions were on
# the machine that built the image. Done here, in the build stage, so the final stage's single
# copy carries it and the image holds one layer of these files rather than two.
RUN chmod -R a+rX /app

FROM python:3.13-slim

WORKDIR /app
COPY --from=build /app /app
ENV PATH=/app/.venv/bin:$PATH \
    FASTEMBED_CACHE_PATH=/app/models \
    PYTHONUNBUFFERED=1

# Not root: the job writes only to a temporary directory and the bucket.
RUN useradd --create-home --uid 10001 clippings
USER clippings

# The service binds all interfaces on Cloud Run's PORT; the job overrides the command.
CMD ["sh", "-c", "clippings serve --host 0.0.0.0 --port ${PORT:-8080}"]
