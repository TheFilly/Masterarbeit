# syntax=docker/dockerfile:1
#
# Legacy ScrabbleGAN CPU inference container.
# This image is intentionally separate from the Python 3.13 project.
# Micromamba keeps the historical Python/PyTorch contract while avoiding the
# memory-heavy legacy Conda solver during image builds.

FROM mambaorg/micromamba:2.8.1

ARG SCRABBLEGAN_REPO_URL="https://github.com/amzn/convolutional-handwriting-gan"
ARG SCRABBLEGAN_COMMIT="PIN_UPSTREAM_COMMIT"
ARG SCRABBLEGAN_CHECKPOINT_PATH="/opt/checkpoints/latest_net_G.pth"
ARG SCRABBLEGAN_CHECKPOINT_SHA256="PIN_CHECKPOINT_SHA256"
ARG SCRABBLEGAN_ENV="scrabblegan"

ENV SCRABBLEGAN_REPO_URL="${SCRABBLEGAN_REPO_URL}" \
    SCRABBLEGAN_COMMIT="${SCRABBLEGAN_COMMIT}" \
    SCRABBLEGAN_CHECKPOINT_PATH="${SCRABBLEGAN_CHECKPOINT_PATH}" \
    SCRABBLEGAN_CHECKPOINT_SHA256="${SCRABBLEGAN_CHECKPOINT_SHA256}" \
    SCRABBLEGAN_ENV="${SCRABBLEGAN_ENV}" \
    SCRABBLEGAN_SOURCE_DIR="/opt/scrabblegan/source" \
    HANDWRITING_ASSET_ROOT="/workspace/DycomData/HandwritingAssets" \
    CUDA_VISIBLE_DEVICES=""

USER root

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN micromamba create --yes --name "${SCRABBLEGAN_ENV}" \
        --channel pytorch \
        --channel conda-forge \
        --channel defaults \
        python=3.6.8 \
        pytorch=1.2.0 torchvision=0.4.0 cpuonly \
        "pillow<8" numpy pandas python-lmdb opencv tqdm joblib six dominate visdom scipy scikit-image \
    && micromamba clean --all --yes

RUN mkdir -p \
        "${SCRABBLEGAN_SOURCE_DIR}" \
        "/opt/checkpoints" \
        "${HANDWRITING_ASSET_ROOT}"

COPY scrabblegan_tool /opt/scrabblegan_tool/scrabblegan_tool
COPY wrapper /opt/scrabblegan_tool/wrapper

RUN printf '%s\n' \
        '#!/bin/sh' \
        'PYTHONPATH=/opt/scrabblegan_tool exec /opt/conda/envs/scrabblegan/bin/python -m scrabblegan_tool.cli render "$@"' \
        > /usr/local/bin/scrabblegan-render \
    && printf '%s\n' \
        '#!/bin/sh' \
        'PYTHONPATH=/opt/scrabblegan_tool exec /opt/conda/envs/scrabblegan/bin/python -m scrabblegan_tool.cli validate "$@"' \
        > /usr/local/bin/scrabblegan-validate \
    && chmod +x /usr/local/bin/scrabblegan-render /usr/local/bin/scrabblegan-validate

WORKDIR /workspace

ENV PATH="/opt/conda/envs/${SCRABBLEGAN_ENV}/bin:${PATH}"

# This image never clones ScrabbleGAN or downloads model weights. Mount pinned
# source/checkpoint artifacts from DycomData/HandwritingAssets at runtime.
CMD ["/bin/bash", "-lc", "scrabblegan-render --help && scrabblegan-validate --help"]
