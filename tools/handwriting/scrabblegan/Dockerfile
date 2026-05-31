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
        python3.6 \
        python3.6-dev \
        python3-pip \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p \
        "${SCRABBLEGAN_SOURCE_DIR}" \
        "/opt/checkpoints" \
        "${HANDWRITING_ASSET_ROOT}"

WORKDIR /workspace

# This scaffold does not clone repositories or download checkpoints. Building the
# image still uses configured OS package repositories for Python/bootstrap packages.
CMD ["/bin/bash", "-lc", "echo 'ScrabbleGAN scaffold only. Mount pinned source/checkpoint and run the batch CLI wrapper when implemented.'"]
