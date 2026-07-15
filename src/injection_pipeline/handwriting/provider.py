"""Typed handwriting asset provider with deterministic local cache keys."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from injection_pipeline.config.identifier_schema import IdentifierSchema
from injection_pipeline.engine.handwriting_manifest import load_handwriting_manifest
from injection_pipeline.models.identity import Identity

ALLOWED_HANDWRITING_FIELDS: frozenset[str] = frozenset(
    ("patient_name", "patient_id", "accession_number")
)
HANDWRITING_RENDERER_VERSION = "scrabblegan-soft-alpha-v2"
HANDWRITING_ASSET_MANIFEST_VERSION = "0.1.0-handwriting-assets"
DEFAULT_HANDWRITING_ASSET_ROOT = Path("DycomData") / "HandwritingAssets"
_JSON_INDENT = 2


class HandwritingProviderError(RuntimeError):
    """Base error for handwriting provider failures."""


class MissingHandwritingRuntimeError(HandwritingProviderError):
    """Raised when a cache miss cannot invoke the isolated generator runtime."""


class MissingHandwritingCheckpointError(HandwritingProviderError):
    """Raised when the configured checkpoint is absent or hash-incompatible."""


class HandwritingAlphabetError(HandwritingProviderError):
    """Raised when requested text cannot be represented by the generator."""


class HandwritingCacheMiss(HandwritingProviderError):
    """Raised when assets are missing and no generator was supplied."""


class HandwritingGeneratorOptions(BaseModel):
    """Generator-affecting options that participate in the cache identity."""

    model_config = ConfigDict(extra="forbid")

    generator_name: str = "scrabblegan"
    ink_color: Literal["black", "gray", "white"] = "black"
    background: Literal["transparent", "white"] = "transparent"
    alphabet: str
    options_sha256: str | None = None
    word_gap_px: int = 12
    cpu_only: bool = True
    extra: dict[str, str | int | float | bool | None] = Field(default_factory=dict)

    @field_validator("generator_name", "alphabet")
    @classmethod
    # Input: `value` mit einer Generator-Option aus der Provider-Konfiguration.
    # Output: Nichtleerer Optionswert.
    # Die Funktion verhindert implizite Defaults aus leer konfigurierten
    # Runtime-Werten, bevor Cache-Keys oder Generator-Manifeste entstehen.
    def _validate_non_empty(cls, value: str) -> str:
        if value == "":
            raise ValueError("handwriting generator options must not be empty.")
        return value

    @field_validator("options_sha256")
    @classmethod
    # Input: `value` mit optionalem SHA-256 des Options-Sidecars.
    # Output: Normalisierter Hex-String oder `None`.
    # Die Funktion macht den Sidecar-Hash cachewirksam, sobald der integrierte
    # Pfad ihn aus dem Checkpoint-Vertrag geladen hat.
    def _validate_options_sha(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        if len(normalized) != 64 or any(
            character not in "0123456789abcdef" for character in normalized
        ):
            raise ValueError("options_sha256 must be a SHA-256 hex digest.")
        return normalized

    @field_validator("word_gap_px")
    @classmethod
    # Input: `value` mit Abstand zwischen generierten Wortbildern.
    # Output: Nichtnegativer Pixelabstand.
    # Die Funktion haelt layoutrelevante Generatoroptionen cachewirksam und
    # lehnt ungueltige Werte vor einem externen Aufruf ab.
    def _validate_word_gap(cls, value: int) -> int:
        if value < 0:
            raise ValueError("word_gap_px must be >= 0.")
        return value

    @model_validator(mode="after")
    # Input: `self` mit allen Generatoroptionen.
    # Output: Validierte Generatoroptionen.
    # Die Funktion erzwingt CPU-only Inferenz fuer den Provider-Vertrag und
    # erlaubt keinen stillen GPU- oder Runtime-Fallback.
    def _validate_cpu_only(self) -> HandwritingGeneratorOptions:
        if not self.cpu_only:
            raise ValueError("handwriting generation must be CPU-only.")
        return self


class HandwritingRuntimeConfig(BaseModel):
    """Local runtime inputs required for cache identity and generation."""

    model_config = ConfigDict(extra="forbid")

    checkpoint_path: Path
    checkpoint_sha256: str
    upstream_commit: str
    asset_root: Path = DEFAULT_HANDWRITING_ASSET_ROOT
    source_dir: Path | None = None
    options_sidecar_path: Path | None = None
    generator_command: str | None = None

    @field_validator("checkpoint_sha256")
    @classmethod
    # Input: `value` mit erwartetem SHA-256 des Checkpoints.
    # Output: Normalisierter Hex-String.
    # Die Funktion macht den Checkpoint-Hash verpflichtend, da er Teil der
    # Cache-Identitaet ist.
    def _validate_checkpoint_sha(cls, value: str) -> str:
        normalized = value.strip().lower()
        if len(normalized) != 64 or any(
            character not in "0123456789abcdef" for character in normalized
        ):
            raise ValueError("checkpoint_sha256 must be a SHA-256 hex digest.")
        return normalized

    @field_validator("upstream_commit")
    @classmethod
    # Input: `value` mit Upstream-Commit des isolierten Generators.
    # Output: Nichtleerer Commit-String.
    # Die Funktion verhindert Cache-Wiederverwendung ohne versionierte
    # Upstream-Herkunft.
    def _validate_upstream_commit(cls, value: str) -> str:
        commit = value.strip()
        if commit == "":
            raise ValueError("upstream_commit must not be empty.")
        return commit


class HandwritingCacheIdentity(BaseModel):
    """Complete deterministic identity for one cached handwriting asset."""

    model_config = ConfigDict(extra="forbid")

    seed: int
    schema_id: str
    schema_version: str
    field: str
    text: str
    checkpoint_sha256: str
    upstream_commit: str
    generator_options: dict[str, Any]

    @property
    # Input: Keine Parameter.
    # Output: Stabiler SHA-256-Key fuer diese Asset-Identitaet.
    # Die Property serialisiert sortiert und ohne lokale Pfade, damit gleiche
    # fachliche Inputs denselben Cache-Key ergeben.
    def cache_key(self) -> str:
        payload = self.model_dump(mode="json")
        encoded = json.dumps(
            payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


class RequestedHandwritingAsset(BaseModel):
    """One requested visible field after schema and alphabet validation."""

    model_config = ConfigDict(extra="forbid")

    asset_id: str
    identity: HandwritingCacheIdentity
    render_text: str

    @property
    # Input: Keine Parameter.
    # Output: Identity-Feldname fuer das Generator-Manifest.
    # Die Property vermeidet doppelte Feldhaltung ausserhalb der Cache-Identity.
    def field(self) -> str:
        return self.identity.field

    @property
    # Input: Keine Parameter.
    # Output: Zu rendernder Text fuer das Generator-Manifest.
    # Die Property liefert den normalisierten Text fuer den Generator.
    def text(self) -> str:
        return self.render_text

    @property
    # Input: Keine Parameter.
    # Output: Ursprünglicher Faker-/Identity-Text.
    # Dieser Wert bleibt für Cache-Identität, Ground Truth und Annotationen erhalten.
    def source_text(self) -> str:
        return self.identity.text


class HandwritingGenerationRequest(BaseModel):
    """Typed boundary object for isolated external generator execution."""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    input_manifest_path: Path
    output_root: Path
    run_id: str
    source_dir: Path | None
    options_sidecar_path: Path | None
    checkpoint_path: Path
    checkpoint_sha256: str
    upstream_commit: str
    generator_command: str | None
    options: HandwritingGeneratorOptions
    assets: list[RequestedHandwritingAsset]


class HandwritingGenerationResult(BaseModel):
    """Result returned by an external handwriting generator implementation."""

    model_config = ConfigDict(extra="forbid")

    manifest_path: Path


class GeneratedHandwritingManifest(BaseModel):
    """Provider output for integration with existing manifest attachment logic."""

    model_config = ConfigDict(extra="forbid")

    manifest_path: Path
    assets: dict[str, dict[str, Any]]
    asset_mappings: dict[str, str]
    generated_asset_ids: list[str]
    cache_hit_asset_ids: list[str]


class HandwritingGenerator(Protocol):
    """Execution boundary for Docker or another isolated legacy runtime."""

    # Input: `request` mit Batch-Manifest, Runtime-Kontext und Asset-Liste.
    # Output: Pfad zum Generator-Output-Manifest.
    # Die Implementierung darf externe Prozesse starten und muss Fehler ohne
    # Fallback an den Provider durchreichen.
    def generate(
        self, request: HandwritingGenerationRequest
    ) -> HandwritingGenerationResult: ...


class CommandHandwritingGenerator:
    """Subprocess-based generator adapter for an isolated command or Docker."""

    # Input: `base_command` als ausfuehrbare Argumentliste.
    # Output: Neue Command-Generator-Instanz.
    # Die Klasse haengt den stabilen ScrabbleGAN-Batchvertrag an und setzt fuer
    # den Kindprozess eine CPU-only Umgebung.
    def __init__(self, base_command: Sequence[str]) -> None:
        self._base_command = tuple(base_command)

    # Input: `request` mit Manifesten, Checkpoint und Generatoroptionen.
    # Output: Manifestpfad des externen Renderlaufs.
    # Die Funktion ruft die konfigurierte Runtime ohne Shell auf und bricht bei
    # fehlender Runtime oder nicht erfolgreichem Prozess hart ab.
    def generate(
        self, request: HandwritingGenerationRequest
    ) -> HandwritingGenerationResult:
        if not self._base_command:
            raise MissingHandwritingRuntimeError(
                "Handwriting generator runtime command is empty."
            )
        executable = self._base_command[0]
        if Path(executable).parent == Path(".") and shutil.which(executable) is None:
            raise MissingHandwritingRuntimeError(
                f"Handwriting generator runtime not found: {executable}"
            )

        command = [
            *self._base_command,
            "--input",
            str(request.input_manifest_path),
            "--output-root",
            str(request.output_root),
            "--run-id",
            request.run_id,
            "--checkpoint",
            str(request.checkpoint_path),
            "--checkpoint-sha256",
            request.checkpoint_sha256,
        ]
        if request.source_dir is not None:
            command.extend(["--source-dir", str(request.source_dir)])
        if request.options_sidecar_path is not None:
            command.extend(["--options-json", str(request.options_sidecar_path)])
        if request.generator_command is not None:
            command.extend(["--generator-command", request.generator_command])

        environment = os.environ.copy()
        environment["CUDA_VISIBLE_DEVICES"] = ""
        environment["INJECTION_PIPELINE_HANDWRITING_CPU_ONLY"] = "1"
        completed = subprocess.run(
            command,
            capture_output=True,
            check=False,
            env=environment,
            text=True,
        )
        if completed.returncode != 0:
            raise HandwritingProviderError(
                "Handwriting generator failed with exit code "
                f"{completed.returncode}: {completed.stderr.strip()}"
            )
        manifest_path = request.output_root / request.run_id / "manifest.jsonl"
        if not manifest_path.exists():
            raise HandwritingProviderError(
                f"Handwriting generator did not write manifest: {manifest_path}"
            )
        return HandwritingGenerationResult(manifest_path=manifest_path)


class DockerHandwritingGenerator:
    """Docker-backed generator that mounts the repository as ``/workspace``."""

    # Input: `image` als Docker-Tag und `workspace_root` als Host-Projektwurzel.
    # Output: Neue Docker-Generator-Instanz.
    # Die Instanz verwendet das bereits gebaute Image und übersetzt alle
    # projektinternen Pfade beim Cache-Miss in den Containerpfad `/workspace`.
    def __init__(self, image: str, workspace_root: Path) -> None:
        self._image = image
        self._workspace_root = workspace_root.resolve()

    # Input: `request` mit Host-Pfaden für Manifest, Assets, Source und Checkpoint.
    # Output: Manifestpfad des externen Docker-Laufs.
    # Die Funktion prüft das Image, startet einen kurzlebigen CPU-Container und
    # schreibt die generierten Dateien über den Workspace-Mount zurück auf den Host.
    def generate(
        self, request: HandwritingGenerationRequest
    ) -> HandwritingGenerationResult:
        self._ensure_docker_image()
        command = [
            "docker",
            "run",
            "--rm",
            "--env",
            "CUDA_VISIBLE_DEVICES=",
            "--mount",
            f"type=bind,source={self._workspace_root},target=/workspace",
            self._image,
            "scrabblegan-render",
            "--input",
            self._container_path(request.input_manifest_path),
            "--output-root",
            self._container_path(request.output_root),
            "--run-id",
            request.run_id,
            "--source-dir",
            self._container_path(self._required_path(request.source_dir, "source")),
            "--checkpoint",
            self._container_path(request.checkpoint_path),
            "--checkpoint-sha256",
            request.checkpoint_sha256,
        ]
        if request.options_sidecar_path is not None:
            command.extend(
                [
                    "--options-json",
                    self._container_path(request.options_sidecar_path),
                ]
            )
        if request.generator_command is not None:
            command.extend(["--generator-command", request.generator_command])

        completed = subprocess.run(
            command,
            capture_output=True,
            check=False,
            text=True,
            cwd=str(self._workspace_root),
        )
        if completed.returncode != 0:
            raise HandwritingProviderError(
                "Docker handwriting generator failed with exit code "
                f"{completed.returncode}: {completed.stderr.strip()}"
            )
        manifest_path = request.output_root / request.run_id / "manifest.jsonl"
        if not manifest_path.exists():
            raise HandwritingProviderError(
                f"Docker generator did not write manifest: {manifest_path}"
            )
        return HandwritingGenerationResult(manifest_path=manifest_path)

    # Input: Keine Parameter.
    # Output: Keine Rückgabe.
    # Die Funktion stellt sicher, dass Docker erreichbar ist und das erwartete
    # Image bereits gebaut wurde; ein ungewollter Pull wird verhindert.
    def _ensure_docker_image(self) -> None:
        if shutil.which("docker") is None:
            raise MissingHandwritingRuntimeError(
                "Docker executable not found; build and start Docker Desktop."
            )
        completed = subprocess.run(
            ["docker", "image", "inspect", self._image],
            capture_output=True,
            check=False,
            text=True,
        )
        if completed.returncode != 0:
            raise MissingHandwritingRuntimeError(
                f"Docker image not found: {self._image}. "
                "Build it with docker build first."
            )

    # Input: `path` als Host-Dateipfad innerhalb des Workspace-Mounts.
    # Output: Absoluter Linux-Pfad unter `/workspace`.
    # Die Funktion verhindert, dass der Container ungemountete Host-Pfade
    # erhält; externe Pfade müssen explizit über einen eigenen Runtime-Override
    # eingebunden werden.
    def _container_path(self, path: Path) -> str:
        resolved = path.resolve()
        try:
            relative = resolved.relative_to(self._workspace_root)
        except ValueError as exc:
            raise HandwritingProviderError(
                f"Handwriting path must be inside project workspace: {resolved}"
            ) from exc
        return "/workspace/" + relative.as_posix()

    # Input: Optionale Host-Pfadangabe und fachlicher Pfadname.
    # Output: Nichtleerer Pfad.
    # Die Funktion erzeugt eine klare Provider-Fehlermeldung vor dem Docker-Aufruf.
    @staticmethod
    def _required_path(path: Path | None, name: str) -> Path:
        if path is None:
            raise HandwritingProviderError(f"Docker generator requires {name} path.")
        return path


class HandwritingAssetProvider:
    """Deterministic provider for visible handwriting assets."""

    # Input: `runtime` mit Checkpoint/Asset-Root, `options` mit Generatoroptionen.
    # Output: Neue Provider-Instanz.
    # Der Provider schreibt Cache-Bundles unter `asset_root` und ruft den
    # Generator nur bei fehlenden Assets auf.
    def __init__(
        self,
        runtime: HandwritingRuntimeConfig,
        options: HandwritingGeneratorOptions,
        generator: HandwritingGenerator | None = None,
    ) -> None:
        self._runtime = runtime
        self._options = options
        self._generator = generator

    # Input: `identity`, `schema` und optionaler Generator fuer diesen Aufruf.
    # Output: Cache-Manifest, Asset-Mapping und Hit/Miss-Listen.
    # Die Funktion validiert Checkpoint und Alphabet, erzeugt fehlende Assets
    # ueber die isolierte Runtime und schreibt Manifest/Artefakte robust lokal.
    def resolve_assets(
        self,
        identity: Identity,
        schema: IdentifierSchema,
        generator: HandwritingGenerator | None = None,
    ) -> GeneratedHandwritingManifest:
        _validate_checkpoint(
            self._runtime.checkpoint_path, self._runtime.checkpoint_sha256
        )
        requested_assets = _build_requested_assets(
            identity=identity,
            schema=schema,
            runtime=self._runtime,
            options=self._options,
        )
        bundle_dir = _bundle_dir(self._runtime.asset_root, identity.seed)
        manifest_path = bundle_dir / "manifest.json"
        existing_assets = _load_existing_assets(manifest_path)
        hits, missing = _split_hits(requested_assets, existing_assets)
        generated_ids: list[str] = []

        if missing:
            active_generator = generator or self._generator
            if active_generator is None:
                raise HandwritingCacheMiss(
                    "Handwriting cache miss and no isolated generator was supplied."
                )
            generated_assets = self._generate_missing_assets(
                missing, bundle_dir, active_generator
            )
            existing_assets.update(generated_assets)
            generated_ids = [asset.asset_id for asset in missing]
            _write_cache_manifest_atomic(
                manifest_path=manifest_path,
                seed=identity.seed,
                assets=list(existing_assets.values()),
            )

        assets = (
            load_handwriting_manifest(manifest_path) if manifest_path.exists() else {}
        )
        asset_mappings = {asset.field: asset.asset_id for asset in requested_assets}
        return GeneratedHandwritingManifest(
            manifest_path=manifest_path,
            assets=assets,
            asset_mappings=asset_mappings,
            generated_asset_ids=generated_ids,
            cache_hit_asset_ids=[asset.asset_id for asset in hits],
        )

    # Input: Fehlende Assets, Bundle-Ordner und isolierter Generator.
    # Output: Cache-Manifest-Records fuer die neu erzeugten Assets.
    # Die Funktion schreibt ein Batch-Manifest, laesst extern generieren und
    # uebernimmt Artefakte erst nach vollstaendiger Manifestvalidierung.
    def _generate_missing_assets(
        self,
        missing: list[RequestedHandwritingAsset],
        bundle_dir: Path,
        generator: HandwritingGenerator,
    ) -> dict[str, dict[str, Any]]:
        bundle_dir.mkdir(parents=True, exist_ok=True)
        work_root = bundle_dir / ".work"
        work_root.mkdir(parents=True, exist_ok=True)
        run_id = _run_id_for_missing(missing)
        with tempfile.TemporaryDirectory(
            prefix=f"{run_id}-", dir=work_root
        ) as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            input_manifest_path = temp_dir / "input.jsonl"
            _write_generator_input_manifest_atomic(
                input_manifest_path, missing, self._options
            )
            request = HandwritingGenerationRequest(
                input_manifest_path=input_manifest_path,
                output_root=temp_dir / "generated",
                run_id=run_id,
                source_dir=self._runtime.source_dir,
                options_sidecar_path=self._runtime.options_sidecar_path,
                checkpoint_path=self._runtime.checkpoint_path,
                checkpoint_sha256=self._runtime.checkpoint_sha256,
                upstream_commit=self._runtime.upstream_commit,
                generator_command=self._runtime.generator_command,
                options=self._options,
                assets=missing,
            )
            result = generator.generate(request)
            records = _load_and_validate_generated_manifest(
                result.manifest_path,
                missing,
                self._runtime,
                self._options,
            )
            return _persist_generated_assets(bundle_dir, records)


# Input: Checkpoint-Pfad und erwarteter SHA-256.
# Output: Keine Rueckgabe.
# Die Funktion bricht vor Cache-Lookup oder Generatoraufruf ab, wenn der lokale
# Checkpoint fehlt oder nicht exakt zur konfigurierten Identitaet passt.
def _validate_checkpoint(checkpoint_path: Path, checkpoint_sha256: str) -> None:
    if not checkpoint_path.exists():
        raise MissingHandwritingCheckpointError(
            f"Handwriting checkpoint not found: {checkpoint_path}"
        )
    actual_sha256 = _sha256_file(checkpoint_path)
    if actual_sha256 != checkpoint_sha256:
        raise MissingHandwritingCheckpointError(
            "Handwriting checkpoint SHA-256 mismatch: expected "
            f"{checkpoint_sha256}, got {actual_sha256}."
        )


# Input: `identity`, `schema`, Runtime und Generatoroptionen.
# Output: Liste cacheadressierter Asset-Anfragen fuer sichtbare erlaubte Felder.
# Die Funktion ignoriert tag-only Felder, lehnt unerwartete sichtbare Felder ab
# und validiert das Alphabet ohne Ersatz- oder Font-Fallback.
def _build_requested_assets(
    identity: Identity,
    schema: IdentifierSchema,
    runtime: HandwritingRuntimeConfig,
    options: HandwritingGeneratorOptions,
) -> list[RequestedHandwritingAsset]:
    visible_fields = schema.visible_fields
    unsupported_visible_fields = [
        field.name
        for field in visible_fields
        if field.name not in ALLOWED_HANDWRITING_FIELDS
    ]
    if unsupported_visible_fields:
        raise ValueError(
            "Handwriting is only supported for visible fields "
            f"{sorted(ALLOWED_HANDWRITING_FIELDS)}; got "
            f"{unsupported_visible_fields}."
        )

    requested_assets: list[RequestedHandwritingAsset] = []
    generator_options = {
        **options.model_dump(mode="json"),
        "renderer_version": HANDWRITING_RENDERER_VERSION,
        "text_normalization": "dicom-person-name-separators-v1",
    }
    for field in visible_fields:
        text = identity.fields.get(field.name)
        if text is None:
            continue
        render_text = _render_text_for_handwriting(field.name, text, options.alphabet)
        _validate_alphabet(field.name, render_text, options.alphabet)
        cache_identity = HandwritingCacheIdentity(
            seed=identity.seed,
            schema_id=schema.schema_id,
            schema_version=schema.version,
            field=field.name,
            text=text,
            checkpoint_sha256=runtime.checkpoint_sha256,
            upstream_commit=runtime.upstream_commit,
            generator_options=generator_options,
        )
        requested_assets.append(
            RequestedHandwritingAsset(
                asset_id=_asset_id(field.name, cache_identity.cache_key),
                identity=cache_identity,
                render_text=render_text,
            )
        )
    return requested_assets


# Input: Feldname, Text und Generatoralphabet.
# Output: Keine Rueckgabe.
# Die Funktion meldet das erste nicht darstellbare Zeichen hart, statt auf
# Font-Rendering oder Textveraenderung auszuweichen.
def _validate_alphabet(field: str, text: str, alphabet: str) -> None:
    allowed_characters = set(alphabet)
    for character in text:
        if character not in allowed_characters:
            raise HandwritingAlphabetError(
                f"Field {field!r} contains character {character!r} outside "
                "the handwriting checkpoint alphabet."
            )


# Input: Identity-Feld, originaler Text und Checkpoint-Alphabet.
# Output: Text für den Handschriftgenerator.
# Die Funktion ersetzt nur DICOM-Person-Name-Separatoren, die das konkrete
# ScrabbleGAN-Alphabet nicht kennt; der Originaltext bleibt unverändert erhalten.
def _render_text_for_handwriting(field: str, text: str, alphabet: str) -> str:
    if field != "patient_name":
        return text
    allowed_characters = set(alphabet)
    normalized = text.replace("^", " ").replace("=", " ")
    if all(character in allowed_characters for character in normalized):
        return normalized
    return text


# Input: Asset-Root und Seed.
# Output: Ordner fuer das seedbasierte Cache-Bundle.
# Die Funktion haelt alle Provider-Artefakte unter `DycomData/HandwritingAssets`
# oder einem explizit gesetzten Test-/Integrationsroot.
def _bundle_dir(asset_root: Path, seed: int) -> Path:
    return asset_root / f"seed-{seed}"


# Input: Manifestpfad zu einem vorhandenen Cache-Bundle.
# Output: Mapping Asset-ID auf rohe Manifest-Records.
# Die Funktion verwendet die bestehende Manifestlogik zur Artefaktpruefung und
# gibt danach pfadrelative Records fuer atomare Manifestupdates zurueck.
def _load_existing_assets(manifest_path: Path) -> dict[str, dict[str, Any]]:
    if not manifest_path.exists():
        return {}
    loaded_assets = load_handwriting_manifest(manifest_path)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw_assets = payload.get("assets", [])
    if not isinstance(raw_assets, list):
        raise ValueError("Handwriting cache manifest must contain an assets list.")
    expected_ids = set(loaded_assets)
    records: dict[str, dict[str, Any]] = {}
    for raw_asset in raw_assets:
        if not isinstance(raw_asset, dict):
            continue
        asset_id = str(raw_asset.get("asset_id", ""))
        if asset_id in expected_ids:
            records[asset_id] = dict(raw_asset)
    return records


# Input: Angefragte Assets und bestehende Cache-Records.
# Output: Tupel aus Cache-Hits und fehlenden Assets.
# Die Funktion prueft neben Asset-ID auch die eingebettete Cache-Identitaet,
# damit manuell veraenderte Manifeste nicht still wiederverwendet werden.
def _split_hits(
    requested_assets: list[RequestedHandwritingAsset],
    existing_assets: dict[str, dict[str, Any]],
) -> tuple[list[RequestedHandwritingAsset], list[RequestedHandwritingAsset]]:
    hits: list[RequestedHandwritingAsset] = []
    missing: list[RequestedHandwritingAsset] = []
    for requested_asset in requested_assets:
        existing = existing_assets.get(requested_asset.asset_id)
        if existing is None or not _cache_identity_matches(requested_asset, existing):
            missing.append(requested_asset)
        else:
            hits.append(requested_asset)
    return hits, missing


# Input: Angefragtes Asset und vorhandener Manifest-Record.
# Output: `True`, wenn Cache-Key und Identitaet exakt uebereinstimmen.
# Die Funktion verhindert Wiederverwendung alter Artefakte nach Schema-,
# Checkpoint-, Commit-, Text- oder Generatoroptionswechseln.
def _cache_identity_matches(
    requested_asset: RequestedHandwritingAsset, existing_record: dict[str, Any]
) -> bool:
    raw_identity = existing_record.get("cache_identity")
    if not isinstance(raw_identity, dict):
        return False
    if raw_identity.get("cache_key") != requested_asset.identity.cache_key:
        return False
    expected_identity = requested_asset.identity.model_dump(mode="json")
    for key, value in expected_identity.items():
        if raw_identity.get(key) != value:
            return False
    return True


# Input: Zielpfad, fehlende Asset-Anfragen und Generatoroptionen.
# Output: Keine Rueckgabe.
# Die Funktion schreibt das JSONL-Inputmanifest atomar mit stabilem Vertrag fuer
# die isolierte ScrabbleGAN-Runtime.
def _write_generator_input_manifest_atomic(
    manifest_path: Path,
    missing: list[RequestedHandwritingAsset],
    options: HandwritingGeneratorOptions,
) -> None:
    records = [
        {
            "asset_id": asset.asset_id,
            "field": asset.field,
            "text": asset.render_text,
            "ink_color": options.ink_color,
            "background": options.background,
            "seed": asset.identity.seed,
        }
        for asset in missing
    ]
    lines = [
        json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
        for record in records
    ]
    _write_text_atomic(manifest_path, "".join(lines))


# Input: Generator-Manifest, erwartete Assets, Runtime und Optionen.
# Output: Mapping Asset-ID auf validierte Generator-Records mit absoluten Quellen.
# Die Funktion akzeptiert nur relative Pfade, passende Hashes, erwartete Commits
# und vollstaendige Ergebnisse fuer alle angefragten Cache-Misses.
def _load_and_validate_generated_manifest(
    manifest_path: Path,
    expected_assets: list[RequestedHandwritingAsset],
    runtime: HandwritingRuntimeConfig,
    options: HandwritingGeneratorOptions,
) -> dict[str, dict[str, Any]]:
    if not manifest_path.exists():
        raise HandwritingProviderError(
            f"Handwriting generator manifest not found: {manifest_path}"
        )
    manifest_root = manifest_path.parent
    expected_by_id = {asset.asset_id: asset for asset in expected_assets}
    records: dict[str, dict[str, Any]] = {}
    for line_number, raw_line in enumerate(
        manifest_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not raw_line.strip():
            continue
        payload = json.loads(raw_line)
        if not isinstance(payload, dict):
            raise HandwritingProviderError(
                f"Generated manifest line {line_number} must be an object."
            )
        asset_id = str(payload.get("asset_id", ""))
        expected = expected_by_id.get(asset_id)
        if expected is None:
            continue
        _validate_generated_record(
            payload, expected, manifest_root, runtime, options, line_number
        )
        source_text = payload.get("source_text", expected.source_text)
        if source_text != expected.source_text:
            raise HandwritingProviderError(
                f"Generated manifest line {line_number} has incompatible source_text."
            )
        payload["source_text"] = expected.source_text
        payload["_source_manifest_root"] = manifest_root
        payload["_cache_identity"] = expected.identity
        records[asset_id] = payload

    missing_ids = sorted(set(expected_by_id) - set(records))
    if missing_ids:
        raise HandwritingProviderError(
            f"Handwriting generator did not produce requested assets: {missing_ids}"
        )
    return records


# Input: Generator-Record, erwartetes Asset und Runtime-Kontext.
# Output: Keine Rueckgabe.
# Die Funktion prueft Feld/Text/Seed, Checkpoint, Commit, Optionen, relative
# Pfade und Bild-/Maskenhashes fuer einen einzelnen Output-Record.
def _validate_generated_record(
    record: dict[str, Any],
    expected: RequestedHandwritingAsset,
    manifest_root: Path,
    runtime: HandwritingRuntimeConfig,
    options: HandwritingGeneratorOptions,
    line_number: int,
) -> None:
    required_values = {
        "field": expected.field,
        "text": expected.text,
        "checkpoint_sha256": runtime.checkpoint_sha256,
        "scrabblegan_commit": runtime.upstream_commit,
        "ink_color": options.ink_color,
        "background": options.background,
        "seed": expected.identity.seed,
    }
    if options.options_sha256 is not None:
        required_values["generator_options_sha256"] = options.options_sha256
    for key, expected_value in required_values.items():
        if record.get(key) != expected_value:
            raise HandwritingProviderError(
                f"Generated manifest line {line_number} has incompatible {key}."
            )
    for key in ("image_path", "mask_path", "image_sha256", "mask_sha256"):
        if key not in record:
            raise HandwritingProviderError(
                f"Generated manifest line {line_number} missing {key}."
            )

    image_path = _resolve_relative_path(manifest_root, str(record["image_path"]))
    mask_path = _resolve_relative_path(manifest_root, str(record["mask_path"]))
    if _sha256_file(image_path) != record["image_sha256"]:
        raise HandwritingProviderError(
            f"Generated image hash mismatch for asset {expected.asset_id}."
        )
    if _sha256_file(mask_path) != record["mask_sha256"]:
        raise HandwritingProviderError(
            f"Generated mask hash mismatch for asset {expected.asset_id}."
        )


# Input: Bundle-Ordner und validierte Generator-Records.
# Output: Cache-Manifest-Records mit relativen Pfaden im Bundle.
# Die Funktion kopiert Bild und Maske atomar in den Cache und erzeugt Records
# ohne absolute Pfade fuer das persistierte Manifest.
def _persist_generated_assets(
    bundle_dir: Path, records: dict[str, dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    persisted_records: dict[str, dict[str, Any]] = {}
    for asset_id, record in records.items():
        source_root = Path(record["_source_manifest_root"])
        source_image = _resolve_relative_path(source_root, str(record["image_path"]))
        source_mask = _resolve_relative_path(source_root, str(record["mask_path"]))
        image_path = bundle_dir / "images" / f"{asset_id}.png"
        mask_path = bundle_dir / "masks" / f"{asset_id}-mask.png"
        _copy_file_atomic(source_image, image_path)
        _copy_file_atomic(source_mask, mask_path)

        cache_identity = record["_cache_identity"]
        persisted_record = {
            key: value for key, value in record.items() if not key.startswith("_")
        }
        persisted_record.update(
            {
                "identity_field": record["field"],
                "background_mode": record["background"],
                "image_path": _relative_posix(bundle_dir, image_path),
                "mask_path": _relative_posix(bundle_dir, mask_path),
                "image_sha256": _sha256_file(image_path),
                "mask_sha256": _sha256_file(mask_path),
                "cache_identity": {
                    "cache_key": cache_identity.cache_key,
                    **cache_identity.model_dump(mode="json"),
                },
            }
        )
        persisted_records[asset_id] = persisted_record
    return persisted_records


# Input: Manifestpfad, Seed und Asset-Records.
# Output: Keine Rueckgabe.
# Die Funktion schreibt das Cache-Manifest atomar und sortiert Assets stabil nach
# Asset-ID, ohne lokale absolute Pfade aufzunehmen.
def _write_cache_manifest_atomic(
    manifest_path: Path, seed: int, assets: list[dict[str, Any]]
) -> None:
    payload = {
        "schema_version": HANDWRITING_ASSET_MANIFEST_VERSION,
        "bundle": {"seed": seed},
        "assets": sorted(assets, key=lambda asset: str(asset.get("asset_id", ""))),
    }
    _write_text_atomic(
        manifest_path,
        json.dumps(payload, ensure_ascii=False, indent=_JSON_INDENT, sort_keys=True)
        + "\n",
    )


# Input: Manifest-Wurzel und relativer Asset-Pfad.
# Output: Absoluter Pfad innerhalb der Manifest-Wurzel.
# Die Funktion verhindert absolute Pfade und Parent-Traversal in Generator- und
# Cache-Manifesten.
def _resolve_relative_path(root: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        raise HandwritingProviderError(
            f"Handwriting manifest path must be relative: {path}"
        )
    normalized = Path(os.path.normpath(raw_path))
    if normalized.parts and normalized.parts[0] == "..":
        raise HandwritingProviderError(
            f"Handwriting manifest path leaves its root: {raw_path}"
        )
    resolved = root / normalized
    if not resolved.exists():
        raise HandwritingProviderError(f"Handwriting artifact not found: {resolved}")
    return resolved


# Input: Basisordner und Zielpfad.
# Output: POSIX-artiger relativer Pfad.
# Die Funktion verhindert versehentliche absolute Manifestpfade im Cache-Bundle.
def _relative_posix(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


# Input: Feldname und Cache-Key.
# Output: Stabiler Asset-Identifier fuer Manifest und Artefaktnamen.
# Die Funktion nutzt den vollen Cache-Key fuer Kollisionssicherheit in der
# eingebetteten Identitaet und eine kurze lesbare Asset-ID fuer Dateinamen.
def _asset_id(field: str, cache_key: str) -> str:
    return f"{field}-{cache_key[:20]}"


# Input: Fehlende Assets.
# Output: Stabiler Run-ID-String fuer einen Generator-Batch.
# Die Funktion macht temporäre Generatorausgaben reproduzierbar benannt, ohne
# lokale Pfade in die Cache-Identitaet aufzunehmen.
def _run_id_for_missing(missing: list[RequestedHandwritingAsset]) -> str:
    digest = hashlib.sha256()
    for asset in missing:
        digest.update(asset.asset_id.encode("utf-8"))
    return f"handwriting-{digest.hexdigest()[:16]}"


# Input: Zielpfad und Textinhalt.
# Output: Keine Rueckgabe.
# Die Funktion schreibt zuerst in eine Temp-Datei im Zielordner und ersetzt den
# Zielpfad danach atomar.
def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as temp_file:
        temp_path = Path(temp_file.name)
        temp_file.write(text)
    os.replace(temp_path, path)


# Input: Quell- und Zielpfad.
# Output: Keine Rueckgabe.
# Die Funktion kopiert in eine Temp-Datei im Zielordner und ersetzt danach
# atomar, damit halbe Bild-/Maskendateien nicht manifestiert werden.
def _copy_file_atomic(source_path: Path, target_path: Path) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("wb", dir=target_path.parent, delete=False) as fh:
        temp_path = Path(fh.name)
    try:
        shutil.copyfile(source_path, temp_path)
        os.replace(temp_path, target_path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


# Input: Datei-Pfad.
# Output: SHA-256-Hexdigest des Dateiinhalts.
# Die Funktion streamt die Datei fuer Checkpoints und erzeugte Artefakte.
def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
