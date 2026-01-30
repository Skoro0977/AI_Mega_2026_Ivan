FROM python:3.14-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_SYSTEM_PYTHON=1

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
RUN python -m pip install --no-cache-dir uv \
    && uv sync --frozen --no-dev

COPY src ./src
COPY prompts ./prompts
COPY examples ./examples
RUN mkdir -p /app/runs

VOLUME ["/app/runs"]

ENTRYPOINT ["python"]
CMD ["-m", "src.interview_coach.cli"]
