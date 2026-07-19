"""Typed handwriting asset provider and cache API."""

from injection_pipeline.handwriting.options import (
    extract_required_alphabet,
    load_options_sidecar,
    resolve_options_sidecar,
)
from injection_pipeline.handwriting.provider import (
    ALLOWED_HANDWRITING_FIELDS,
    CommandHandwritingGenerator,
    DockerHandwritingGenerator,
    GeneratedHandwritingManifest,
    HandwritingAlphabetError,
    HandwritingAssetProvider,
    HandwritingCacheIdentity,
    HandwritingCacheMiss,
    HandwritingGenerationRequest,
    HandwritingGenerationResult,
    HandwritingGenerator,
    HandwritingGeneratorOptions,
    HandwritingProviderError,
    HandwritingRuntimeConfig,
    HandwritingTextAssetRequest,
    MissingHandwritingCheckpointError,
    MissingHandwritingRuntimeError,
)

__all__ = [
    "ALLOWED_HANDWRITING_FIELDS",
    "CommandHandwritingGenerator",
    "DockerHandwritingGenerator",
    "GeneratedHandwritingManifest",
    "HandwritingAlphabetError",
    "HandwritingAssetProvider",
    "HandwritingCacheIdentity",
    "HandwritingCacheMiss",
    "HandwritingGenerator",
    "HandwritingGeneratorOptions",
    "HandwritingGenerationRequest",
    "HandwritingGenerationResult",
    "HandwritingProviderError",
    "HandwritingRuntimeConfig",
    "HandwritingTextAssetRequest",
    "MissingHandwritingCheckpointError",
    "MissingHandwritingRuntimeError",
    "extract_required_alphabet",
    "load_options_sidecar",
    "resolve_options_sidecar",
]
