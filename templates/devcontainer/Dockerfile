# Local and CI container for offline PySpark tests: Java 17 + Python 3.11 + pinned test libraries.
# Not yet built or run (2 Nov 2026); Tier 7 task SL-072 verifies it.
FROM mcr.microsoft.com/devcontainers/python:3.11-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends openjdk-17-jre-headless && rm -rf /var/lib/apt/lists/*
# On arm64 hosts the path ends in -arm64.
ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64 \
    PYSPARK_PYTHON=python3 PYSPARK_DRIVER_PYTHON=python3 TZ=UTC
COPY requirements-test.txt /tmp/requirements-test.txt
RUN pip install --no-cache-dir -r /tmp/requirements-test.txt
