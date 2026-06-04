# syntax=docker/dockerfile:1
#
# Legacy ScrabbleGAN container scaffold.
# This image is intentionally separate from the Python 3.13 project.

FROM nvidia/cuda:9.0-cudnn7-devel-ubuntu16.04

ARG SCRABBLEGAN_REPO_URL="https://github.com/amzn/convolutional-handwriting-gan"
ARG SCRABBLEGAN_COMMIT="PIN_UPSTREAM_COMMIT"
ARG SCRABBLEGAN_CHECKPOINT_PATH="/opt/checkpoints/scrabblegan.pth"
ARG SCRABBLEGAN_CHECKPOINT_SHA256="PIN_CHECKPOINT_SHA256"
ARG PYTORCH_VERSION="1.2.0"

ENV SCRABBLEGAN_REPO_URL="${SCRABBLEGAN_REPO_URL}" \
    SCRABBLEGAN_COMMIT="${SCRABBLEGAN_COMMIT}" \
    SCRABBLEGAN_CHECKPOINT_PATH="${SCRABBLEGAN_CHECKPOINT_PATH}" \
    SCRABBLEGAN_CHECKPOINT_SHA256="${SCRABBLEGAN_CHECKPOINT_SHA256}" \
    PYTORCH_VERSION="${PYTORCH_VERSION}" \
    SCRABBLEGAN_SOURCE_DIR="/opt/scrabblegan/source" \
    HANDWRITING_ASSET_ROOT="/workspace/DycomData/HandwritingAssets"

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        git \
        python3.6 \
        python3.6-dev \
        python3-pip \
    && rm -rf /var/lib/apt/lists/*

RUN python3.6 -m pip install --no-cache-dir "Pillow<8"

RUN mkdir -p \
        "${SCRABBLEGAN_SOURCE_DIR}" \
        "/opt/checkpoints" \
        "${HANDWRITING_ASSET_ROOT}"

COPY scrabblegan_tool /opt/scrabblegan_tool/scrabblegan_tool

RUN printf '%s\n' \
        '#!/bin/sh' \
        'PYTHONPATH=/opt/scrabblegan_tool exec python3.6 -m scrabblegan_tool.cli render "$@"' \
        > /usr/local/bin/scrabblegan-render \
    && printf '%s\n' \
        '#!/bin/sh' \
        'PYTHONPATH=/opt/scrabblegan_tool exec python3.6 -m scrabblegan_tool.cli validate "$@"' \
        > /usr/local/bin/scrabblegan-validate \
    && chmod +x /usr/local/bin/scrabblegan-render /usr/local/bin/scrabblegan-validate

WORKDIR /workspace

# This image never clones ScrabbleGAN or downloads model weights. Mount pinned
# source/checkpoint artifacts from DycomData/HandwritingAssets at runtime.
CMD ["/bin/bash", "-lc", "scrabblegan-render --help && scrabblegan-validate --help"]
