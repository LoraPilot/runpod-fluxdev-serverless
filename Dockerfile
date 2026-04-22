# syntax=docker/dockerfile:1.7

# Build argument for base image selection
ARG BASE_IMAGE=nvidia/cuda:12.8.1-cudnn-runtime-ubuntu24.04

# Stage 1: Base image with common dependencies
FROM ${BASE_IMAGE} AS base

# Build arguments for this stage with sensible defaults for standalone builds
ARG ENABLE_PYTORCH_UPGRADE=true
ARG PYTORCH_INDEX_URL=https://download.pytorch.org/whl/cu128
ARG PYTORCH_PACKAGES="torch torchvision torchaudio"
ARG EXTRA_PYTHON_PACKAGES=""
ARG EXTRA_PYTHON_INDEX_URL=""
ARG FLUX_DEV_PRELOAD=""
ARG HUGGINGFACE_ACCESS_TOKEN=""

# Prevents prompts from packages asking for user input during installation
ENV DEBIAN_FRONTEND=noninteractive
# Prefer binary wheels over source distributions for faster pip installations
ENV PIP_PREFER_BINARY=1
# Ensures output from python is printed immediately to the terminal without buffering
ENV PYTHONUNBUFFERED=1
# Speed up some cmake builds
ENV CMAKE_BUILD_PARALLEL_LEVEL=8
ENV FLUX_IMAGE_MODEL_PATH=/opt/models/FLUX.1-dev

# Install Python, git and other necessary tools
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    python3.12 \
    python3.12-venv \
    redis-server \
    git \
    wget \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    ffmpeg \
    openssh-server \
    && ln -sf /usr/bin/python3.12 /usr/bin/python \
    && ln -sf /usr/bin/pip3 /usr/bin/pip \
    && rm -rf /var/lib/apt/lists/*

# Create the virtualenv with Python.
RUN python -m venv /opt/venv

# Use the virtual environment for all subsequent commands
ENV VIRTUAL_ENV="/opt/venv"
ENV PATH="/opt/venv/bin:${PATH}"

# Install base Python tooling used by the image.
RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    python -m pip install --upgrade pip setuptools wheel \
    && python -m pip install triton

# Upgrade PyTorch if needed (for newer CUDA versions)
RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    if [ "$ENABLE_PYTORCH_UPGRADE" = "true" ]; then \
      python -m pip install --force-reinstall ${PYTORCH_PACKAGES} --index-url ${PYTORCH_INDEX_URL}; \
    fi

# Install Python runtime dependencies for the handler
ADD requirements.txt ./
RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    python -m pip install -r /requirements.txt

# Optional image-level extras for specific GPU/model stacks.
RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    if [ -n "${EXTRA_PYTHON_PACKAGES}" ]; then \
      if [ -n "${EXTRA_PYTHON_INDEX_URL}" ]; then \
        python -m pip install --index-url ${EXTRA_PYTHON_INDEX_URL} ${EXTRA_PYTHON_PACKAGES}; \
      else \
        python -m pip install ${EXTRA_PYTHON_PACKAGES}; \
      fi; \
    fi

# Download FLUX.1-dev model in diffusers format during build (optional)
# If HUGGINGFACE_ACCESS_TOKEN is not provided, the model will be downloaded at runtime
RUN --mount=type=cache,target=/root/.cache/huggingface,sharing=locked \
    mkdir -p "${FLUX_IMAGE_MODEL_PATH}" && \
    if [ -n "${HUGGINGFACE_ACCESS_TOKEN}" ]; then \
      export HF_TOKEN="${HUGGINGFACE_ACCESS_TOKEN}" && \
      export HF_HUB_ENABLE_HF_TRANSFER=1 && \
      echo "Downloading FLUX.1-dev in diffusers format using huggingface-cli..." && \
      huggingface-cli download black-forest-labs/FLUX.1-dev --local-dir "${FLUX_IMAGE_MODEL_PATH}" --local-dir-use-symlinks False && \
      echo "FLUX.1-dev model download completed successfully."; \
    else \
      echo "HUGGINGFACE_ACCESS_TOKEN not provided - model will be downloaded at runtime"; \
    fi

# Add application code and scripts
ADD src/start.sh src/bootstrap_workspace.sh src/bootstrap_flux.sh handler.py frontend_app.py test_input.json ./
ADD frontend /frontend
RUN chmod +x /start.sh
RUN chmod +x /bootstrap_workspace.sh
RUN chmod +x /bootstrap_flux.sh

# Flux implementation - no ComfyUI components needed

ENV FLUX_DEV_PRELOAD="${FLUX_DEV_PRELOAD}"

# Set the default command to run when starting the container
CMD ["/start.sh"]
