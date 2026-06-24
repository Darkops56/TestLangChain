FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg gcc libjpeg62-turbo-dev zlib1g-dev tzdata \
        libpango-1.0-0 libpangocairo-1.0-0 libcairo2 libffi-dev shared-mime-info \
        && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir --upgrade pip setuptools

COPY src/ .
RUN pip install --no-cache-dir .

RUN mkdir -p /app/media

EXPOSE 8000

CMD ["python", "-m", "community_manager.main"]
