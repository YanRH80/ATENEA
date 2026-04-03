FROM python:3.12-slim

WORKDIR /app

# System deps for marker-pdf OCR
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libsm6 libxrender1 libxext6 \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[all]" 2>/dev/null || pip install --no-cache-dir -e "."

# Copy source
COPY . .

# Data directory
ENV ATENEA_DATA_DIR=/data
VOLUME /data

# Default: run the CLI
ENTRYPOINT ["atenea"]
CMD ["doctor"]
