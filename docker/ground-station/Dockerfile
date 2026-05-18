FROM python:3.11-slim

LABEL maintainer="FreeSat Research Initiative"
LABEL description="FreeSat Ground Station Relay Node"

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    librtlsdr-dev \
    libusb-1.0-0-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir numpy sgp4 aiohttp websockets pyyaml click rich requests grpcio protobuf

# Copy application code
COPY ground_station/ ./ground_station/
COPY protocol/ ./protocol/
COPY ai/ ./ai/
COPY simulation/ ./simulation/
COPY security/ ./security/
COPY dsp/ ./dsp/
COPY scripts/ ./scripts/

# Create data directory
RUN mkdir -p /app/data /app/observations /app/logs

# Fetch initial TLE data
RUN python scripts/fetch_tle.py --all-OpenOrbitLink --output data/OpenOrbitLink_satellites.tle || true

EXPOSE 50051

# Health check
HEALTHCHECK --interval=60s --timeout=5s --retries=3 \
    CMD python -c "import ground_station; print('OK')" || exit 1

ENTRYPOINT ["python", "-m", "ground_station.grpc_server"]
CMD ["--station-id", "FS-GS-DOCKER", "--host", "0.0.0.0", "--port", "50051"]
