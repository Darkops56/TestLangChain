FROM python:3.12-slim

WORKDIR /app

# System deps for Pillow, WeasyPrint (PDF generation), timezones and other native packages
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg gcc libjpeg62-turbo-dev zlib1g-dev tzdata \
        libpango-1.0-0 libpangocairo-1.0-0 libcairo2 libffi-dev shared-mime-info \
        && \
    rm -rf /var/lib/apt/lists/*

# Upgrade pip/setuptools to avoid build-backend issues
RUN pip install --no-cache-dir --upgrade pip setuptools

# Optional real-media fallback assets used when reviewer feedback flags low realism
COPY media/training/ /app/training-media/

# Official brand assets used as exact logo references for image generation
COPY src/frontend/public/assets/images/novit-logo.png src/frontend/public/assets/images/novit-logo-dark.png src/frontend/public/assets/images/novit-isologo.png /app/brand-assets/

# Copy full source then install (pyproject.toml needs package source)
COPY src/agent/ .
RUN pip install --no-cache-dir .

# Media directory for generated images/videos
RUN mkdir -p /app/media

EXPOSE 8000

CMD ["python", "-m", "community_manager.main"]
