FROM python:3.11-slim

LABEL maintainer="FreeSat Research Initiative"
LABEL description="FreeSat Orbital & RF Simulation Environment"

WORKDIR /app

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir numpy sgp4 scipy matplotlib

# Copy simulation code
COPY simulation/ ./simulation/
COPY ai/ ./ai/
COPY protocol/ ./protocol/
COPY dsp/ ./dsp/

RUN mkdir -p /app/results /app/data

ENTRYPOINT ["python"]
CMD ["-m", "simulation.constellation_sim", "--hours", "24"]
