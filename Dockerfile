FROM python:3.12-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.9.21 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --locked

COPY . /app

ARG APP_VERSION=dev
ARG GIT_BRANCH=unknown
ARG GIT_COMMIT=unknown
RUN python -c 'import json, pathlib, sys; pathlib.Path("build-info.json").write_text(json.dumps({"version": sys.argv[1], "branch": sys.argv[2], "commit": sys.argv[3]}) + "\n")' "$APP_VERSION" "$GIT_BRANCH" "$GIT_COMMIT"

CMD ["python", "-m", "sentinel.main"]
