"""Configuration management for gem-transcribe.

Loads settings from (in priority order):
    1. CLI flag overrides (passed to ``get_config``)
    2. Environment variables prefixed ``GEM_TRANSCRIBE_``
    3. ``.env`` file
    4. ``~/.config/gem-transcribe/config.toml``
    5. Built-in defaults
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "gem-transcribe" / "config.toml"


def _load_toml(path: Path) -> dict[str, Any]:
    """Read a TOML config file and flatten the known sections.

    Returns an empty dict if the file does not exist. Sections recognised:
    ``[gcp]``, ``[model]``, ``[storage]``, ``[transcribe]``. Unknown
    top-level scalar keys are passed through; unknown sections are ignored.
    """
    if not path.is_file():
        return {}
    with path.open("rb") as f:
        data = tomllib.load(f)

    flat: dict[str, Any] = {}

    if isinstance(data.get("gcp"), dict):
        gcp = data["gcp"]
        if "project" in gcp:
            flat["project"] = gcp["project"]
        if "location" in gcp:
            flat["location"] = gcp["location"]

    if isinstance(data.get("model"), dict):
        model = data["model"]
        if "name" in model:
            flat["model"] = model["name"]
        if "max_output_tokens" in model:
            flat["max_output_tokens"] = model["max_output_tokens"]

    if isinstance(data.get("storage"), dict):
        storage = data["storage"]
        if "staging_bucket" in storage:
            flat["staging_bucket"] = storage["staging_bucket"]
        if "keep_staging" in storage:
            flat["keep_staging"] = storage["keep_staging"]

    if isinstance(data.get("transcribe"), dict):
        tr = data["transcribe"]
        if "default_languages" in tr:
            flat["default_languages"] = tr["default_languages"]
        if "request_timeout" in tr:
            flat["request_timeout"] = tr["request_timeout"]

    for k, v in data.items():
        if k not in ("gcp", "model", "storage", "transcribe") and not isinstance(v, dict):
            flat[k] = v

    return flat


# Module-level state so that ``settings_customise_sources`` (a classmethod
# called by pydantic-settings without our overrides) can pick up the
# ``--config`` CLI flag value.
_active_config_path: Path = DEFAULT_CONFIG_PATH


def _set_config_path(path: Path | None) -> None:
    global _active_config_path
    _active_config_path = path if path is not None else DEFAULT_CONFIG_PATH


class Config(BaseSettings):
    """gem-transcribe runtime configuration."""

    project: str = Field(default="", description="GCP project ID")
    location: str = Field(default="us-central1", description="GCP location for Vertex AI")
    model: str = Field(default="gemini-2.5-flash", description="Gemini model name")
    max_output_tokens: int = Field(default=65536, description="Maximum output tokens")
    staging_bucket: str = Field(
        default="",
        description="GCS staging bucket URI, e.g. 'gs://my-bucket/gem-transcribe/'",
    )
    keep_staging: bool = Field(
        default=False,
        description="Skip cleanup of uploaded staging objects (debugging only)",
    )
    default_languages: list[str] = Field(
        default_factory=lambda: ["en"],
        description="Default output languages when --lang is not given",
    )
    request_timeout: int = Field(
        default=1800,
        description="Per-request timeout in seconds for Vertex AI calls",
    )

    model_config = {
        "env_prefix": "GEM_TRANSCRIBE_",
        "env_file": ".env",
        "extra": "ignore",
    }

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        from pydantic_settings import InitSettingsSource

        toml_data = _load_toml(_active_config_path)
        toml_source = InitSettingsSource(settings_cls, init_kwargs=toml_data)
        return (init_settings, env_settings, dotenv_settings, toml_source, file_secret_settings)


def get_config(
    *,
    config_path: Path | None = None,
    **overrides: Any,
) -> Config:
    """Load config with optional CLI overrides.

    Empty-string overrides are ignored so that CLI flags can pass ``""`` for
    "unset". Validates that required fields (``project``, ``staging_bucket``)
    are populated.
    """
    _set_config_path(config_path)
    filtered = {k: v for k, v in overrides.items() if v not in (None, "", [])}
    config = Config(**filtered)

    missing: list[str] = []
    if not config.project:
        missing.append("project (GEM_TRANSCRIBE_PROJECT or [gcp].project)")
    if not config.staging_bucket:
        missing.append("staging_bucket (GEM_TRANSCRIBE_STAGING_BUCKET or [storage].staging_bucket)")
    if missing:
        raise ValueError(
            "Missing required configuration: " + ", ".join(missing) + ". "
            "Set them via config.toml, environment variables, or CLI flags."
        )
    if not config.staging_bucket.startswith("gs://"):
        raise ValueError(f"staging_bucket must start with 'gs://', got {config.staging_bucket!r}")

    return config
