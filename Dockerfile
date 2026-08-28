# syntax=docker/dockerfile:1
FROM python:3.13-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Set work directory
WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libmariadb-dev \
    default-libmysqlclient-dev \
    pkg-config \
    python3-dev \
    libssl-dev \
    libffi-dev \
    gcc \
    g++ \
    nano \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Installed here, not in requirements.txt, so it stays outside GitHub's
# dependency graph/Dependabot scanning - it's dev-only either way.
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir 'mysqlclient>=2.2.1'

# Install Python dependencies (kept above the project copy so this layer only
# rebuilds when requirements change, not on every code change)
COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-dev.txt

# Copy project
COPY . .

EXPOSE 8000