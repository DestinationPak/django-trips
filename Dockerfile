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

# Installed here, not as a project dependency, so it stays outside GitHub's
# dependency graph/Dependabot scanning - it's dev-only either way.
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir 'mysqlclient>=2.2.1'

# Copy project
COPY . .

# setuptools-scm derives the package version from git tag history, which
# this image's build context doesn't reliably carry - pretend a version
# instead of failing the build. Runtime deps come from pyproject.toml's
# own [project.dependencies]/[project.optional-dependencies], so there's
# no separate requirements file to install first.
ENV SETUPTOOLS_SCM_PRETEND_VERSION=0.0.0.dev0
RUN pip install --no-cache-dir -e ".[dev]"

EXPOSE 8000