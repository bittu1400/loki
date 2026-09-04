"""Pydantic settings for models.yaml + pipeline.yaml, plus startup
validation of a book vault (specs.md §9-10).

Everything here runs before any API call and fails fast with actionable
messages. Providers, model IDs, required environment variables, manifest
POV resolution, kebab-case filenames, and path containment are all
checked here so the first real failure is never a confusing 404
mid-session.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from novel_engine.core.errors import ConfigError
from novel_engine.core.outline import ChapterEntry, parse_manifest

SLUG_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

#: Known providers -> the env var that must hold their API key.
KNOWN_PROVIDERS: dict[str, str] = {
    "gemini": "GEMINI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "groq": "GROQ_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "nvidia": "NVIDIA_API_KEY",
    "aihubmix": "AIHUBMIX_API_KEY",
    "local": "",  # keyless (ADR-0006)
    "cohere": "COHERE_API_KEY",
    "zai": "GLM_API_KEY",
}

#: Providers that need no credential. The local llama.cpp lane authenticates
#: nothing, so startup validation must not demand a key for it (ADR-0006).
KEYLESS_PROVIDERS = frozenset({"local"})

REQUIRED_FILES = (
    "canon/story-bible.md",
    "canon/style-guide.md",
    "canon/plot-outline.md",
    "canon/continuity-tracker.md",
    "canon/open-threads.md",
    "canon/deepen-queue.md",
    "characters/index.yaml",
    "log/chapter-summary.md",
    "log/next-step.md",
    "config/models.yaml",
    "config/pipeline.yaml",
)


class ModelRoute(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    model: str

    @field_validator("provider")
    @classmethod
    def _provider_known(cls, value: str) -> str:
        if value not in KNOWN_PROVIDERS:
            legal = ", ".join(sorted(KNOWN_PROVIDERS))
            raise ValueError(f"unknown provider {value!r}; known providers: {legal}")
        return value

    @field_validator("model")
    @classmethod
    def _model_present(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("model ID is empty; every route needs an exact model ID")
        return value.strip()


class EditorModels(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary: ModelRoute
    fallback: ModelRoute


class GenerationParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    temperature: float = Field(default=0.9, ge=0.0, le=2.0)
    top_p: float = Field(default=0.95, ge=0.0, le=1.0)
    seed: int | None = None


class ModelsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pov_models: dict[str, ModelRoute] = Field(default_factory=dict)
    fallback_chain: list[ModelRoute] = Field(default_factory=list)
    editor_model: EditorModels
    generation_params: GenerationParams = Field(default_factory=GenerationParams)


class ContextConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    previous_chapter_tail_words: int = Field(default=500, gt=0)
    recent_summaries: int = Field(default=2, ge=0)
    max_locked_facts: int = Field(default=40, ge=0)
    token_budget: int = Field(default=12000, gt=0)


class RetryConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_attempts: int = Field(default=4, ge=1)
    base_delay_seconds: float = Field(default=1.0, ge=0.0)
    jitter: bool = True
    respect_retry_after: bool = True


class EditorialConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    max_repair_attempts: int = Field(default=2, ge=0)
    fail_closed: bool = True


class PipelineConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_words: int = Field(default=1000, gt=0)
    word_tolerance: float = Field(default=0.10, ge=0.0, lt=1.0)
    max_continuation_rounds: int = Field(default=3, ge=0)

    context: ContextConfig = Field(default_factory=ContextConfig)
    retry: RetryConfig = Field(default_factory=RetryConfig)
    editorial: EditorialConfig = Field(default_factory=EditorialConfig)

    # Deferred (ADR-0001) — present so the shape is fixed early.
    auto_publish: bool = False


class CharacterEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file: str
    pov: bool
    model: str

    @field_validator("file")
    @classmethod
    def _kebab(cls, value: str) -> str:
        stem = value.removesuffix(".md")
        if not SLUG_PATTERN.fullmatch(stem):
            raise ValueError(
                f"character file {value!r} is not kebab-case "
                "(lowercase letters, digits, hyphens)"
            )
        return value


def _load_yaml(path: Path) -> object:
    try:
        with path.open(encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
    except OSError as exc:
        raise ConfigError(f"Cannot read {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path} is not valid YAML: {exc}") from exc
    if data is None:
        # An all-comments file (e.g. the template character index) is an
        # intentionally empty document.
        return {}
    if not isinstance(data, dict):
        raise ConfigError(
            f"{path} must contain a YAML mapping at top level; "
            f"got {type(data).__name__}."
        )
    return data


def load_models_config(path: Path) -> ModelsConfig:
    """Parse and validate config/models.yaml."""
    try:
        return ModelsConfig.model_validate(_load_yaml(path))
    except ValueError as exc:
        raise ConfigError(f"{path} is invalid: {exc}") from exc


def load_pipeline_config(path: Path) -> PipelineConfig:
    """Parse and validate config/pipeline.yaml."""
    try:
        return PipelineConfig.model_validate(_load_yaml(path))
    except ValueError as exc:
        raise ConfigError(f"{path} is invalid: {exc}") from exc


def load_character_index(path: Path) -> dict[str, CharacterEntry]:
    """Parse characters/index.yaml: id -> file, pov flag, model key."""
    raw = _load_yaml(path)
    assert isinstance(raw, dict)  # guaranteed by _load_yaml
    characters: dict[str, CharacterEntry] = {}
    for character_id, entry in raw.items():
        if not isinstance(character_id, str) or not SLUG_PATTERN.fullmatch(
            character_id
        ):
            raise ConfigError(
                f"{path}: character id {character_id!r} is not kebab-case "
                "(lowercase letters, digits, hyphens)."
            )
        try:
            characters[character_id] = CharacterEntry.model_validate(entry)
        except ValueError as exc:
            raise ConfigError(f"{path}: character {character_id!r}: {exc}") from exc
    # An empty index is valid for a freshly scaffolded book; the manifest
    # POV check enforces resolution once chapters are planned.
    return characters


def _check_filenames(book_root: Path) -> None:
    for dirpath, dirnames, filenames in os.walk(book_root):
        # Prune hidden directories rather than only skipping their names:
        # a book with its own snapshot repo (ADR-0013) carries a .git
        # full of files like COMMIT_EDITMSG that are not book content and
        # were never going to be kebab-case.
        dirnames[:] = [name for name in dirnames if not name.startswith(".")]
        relative = Path(dirpath).relative_to(book_root)
        for name in [*dirnames, *filenames]:
            if name.startswith("."):
                continue
            stem = name.removesuffix(".md").removesuffix(".yaml").removesuffix(".json")
            if not SLUG_PATTERN.fullmatch(stem):
                raise ConfigError(
                    f"Filename {relative / name!s} is not kebab-case. Rename it "
                    "(lowercase letters, digits, hyphens)."
                )


def _check_env(models: ModelsConfig, env: Mapping[str, str]) -> None:
    routes = [
        *models.pov_models.values(),
        *models.fallback_chain,
        models.editor_model.primary,
        models.editor_model.fallback,
    ]
    providers = sorted({route.provider for route in routes} - KEYLESS_PROVIDERS)
    missing = [
        KNOWN_PROVIDERS[provider]
        for provider in providers
        if not env.get(KNOWN_PROVIDERS[provider], "").strip()
    ]
    if missing:
        raise ConfigError(
            f"Missing API key(s): {', '.join(sorted(set(missing)))}. "
            "Copy .env.example to .env, fill in the keys, and export them "
            "before running."
        )


class BookConfig(BaseModel):
    slug: str
    root: Path
    models: ModelsConfig
    pipeline: PipelineConfig
    characters: dict[str, CharacterEntry]
    manifest: list[ChapterEntry]


def load_book_config(
    vault_root: Path | str,
    slug: str,
    env: Mapping[str, str] | None = None,
) -> BookConfig:
    """Validate everything about a book before any work begins.

    `env` defaults to the process environment; callers that have loaded
    dotenv may pass its mapping instead.
    """
    if env is None:
        env = os.environ

    if not SLUG_PATTERN.fullmatch(slug):
        raise ConfigError(
            f"Book slug {slug!r} is not valid. Use lowercase letters, digits, "
            "and hyphens (e.g. 'the-salt-almanac')."
        )

    vault = Path(vault_root).resolve()
    root = (vault / slug).resolve()
    if root.parent != vault:
        raise ConfigError(
            f"Book path {root} does not resolve directly under {vault}; "
            "refusing to look outside the vault root."
        )
    if not root.is_dir():
        raise ConfigError(
            f"No book directory at {root}. Create one with: new-book --slug {slug}"
        )

    missing_files = [name for name in REQUIRED_FILES if not (root / name).is_file()]
    if missing_files:
        raise ConfigError(
            f"Book {slug!r} is missing required file(s): "
            f"{', '.join(missing_files)}. Re-scaffold with new-book --slug {slug}."
        )

    _check_filenames(root)

    models = load_models_config(root / "config/models.yaml")
    pipeline = load_pipeline_config(root / "config/pipeline.yaml")

    characters = load_character_index(root / "characters/index.yaml")
    for character_id, entry in characters.items():
        if not (root / "characters" / entry.file).is_file():
            raise ConfigError(
                f"characters/index.yaml points character {character_id!r} at "
                f"{entry.file}, which does not exist."
            )
        if entry.pov and entry.model not in models.pov_models:
            raise ConfigError(
                f"Character {character_id!r} is a POV whose model key "
                f"{entry.model!r} has no entry in models.yaml pov_models. "
                "Add a routing entry for it."
            )
    pov_ids = {cid for cid, entry in characters.items() if entry.pov}
    unrouted = pov_ids - set(models.pov_models)
    if unrouted:
        raise ConfigError(
            f"POV character(s) without a models.yaml route: "
            f"{', '.join(sorted(unrouted))}."
        )

    outline_text = (root / "canon/plot-outline.md").read_text(encoding="utf-8")
    manifest = parse_manifest(outline_text)
    unknown_povs = sorted({entry.pov for entry in manifest} - set(characters))
    if unknown_povs:
        raise ConfigError(
            f"Manifest POV(s) {', '.join(unknown_povs)} do not resolve to any "
            "character in characters/index.yaml. Add the character or fix "
            "the manifest."
        )

    _check_env(models, env)

    return BookConfig(
        slug=slug,
        root=root,
        models=models,
        pipeline=pipeline,
        characters=characters,
        manifest=manifest,
    )
