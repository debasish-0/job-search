FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    JOBSEARCH_CONFIG=/app/config/settings.toml

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN python -m pip install --upgrade pip && \
    python -m pip install ".[all]"

COPY config ./config
COPY examples ./examples
RUN mkdir -p /app/data/applications /app/data/digests

EXPOSE 8000 8501

CMD ["jobsearch", "serve", "--host", "0.0.0.0", "--port", "8000"]
