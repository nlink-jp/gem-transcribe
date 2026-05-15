"""Tests for gem_transcribe.config."""

from __future__ import annotations

from pathlib import Path

import pytest

from gem_transcribe import config as config_module
from gem_transcribe.config import Config, _load_toml, get_config


def _write_toml(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


class TestLoadToml:
    def test_returns_empty_when_file_missing(self, tmp_path: Path) -> None:
        assert _load_toml(tmp_path / "missing.toml") == {}

    def test_flattens_known_sections(self, tmp_path: Path) -> None:
        path = tmp_path / "config.toml"
        _write_toml(
            path,
            """
[gcp]
project = "p1"
location = "asia-northeast1"

[model]
name = "gemini-2.5-pro"
max_output_tokens = 4096

[storage]
staging_bucket = "gs://b/"
keep_staging = true

[transcribe]
default_languages = ["en", "ja"]
request_timeout = 600
""",
        )
        flat = _load_toml(path)
        assert flat == {
            "project": "p1",
            "location": "asia-northeast1",
            "model": "gemini-2.5-pro",
            "max_output_tokens": 4096,
            "staging_bucket": "gs://b/",
            "keep_staging": True,
            "default_languages": ["en", "ja"],
            "request_timeout": 600,
        }

    def test_ignores_unknown_sections(self, tmp_path: Path) -> None:
        path = tmp_path / "config.toml"
        _write_toml(path, '[unknown]\nfoo = "bar"\n')
        assert _load_toml(path) == {}


class TestGetConfig:
    def test_loads_from_toml(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        path = tmp_path / "config.toml"
        _write_toml(
            path,
            """
[gcp]
project = "from-toml"
[storage]
staging_bucket = "gs://toml-bucket/"
""",
        )
        monkeypatch.delenv("GEM_TRANSCRIBE_PROJECT", raising=False)
        monkeypatch.delenv("GEM_TRANSCRIBE_STAGING_BUCKET", raising=False)
        cfg = get_config(config_path=path)
        assert cfg.project == "from-toml"
        assert cfg.staging_bucket == "gs://toml-bucket/"
        assert cfg.location == "us-central1"  # default

    def test_env_overrides_toml(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        path = tmp_path / "config.toml"
        _write_toml(
            path,
            """
[gcp]
project = "from-toml"
[storage]
staging_bucket = "gs://toml-bucket/"
""",
        )
        monkeypatch.setenv("GEM_TRANSCRIBE_PROJECT", "from-env")
        cfg = get_config(config_path=path)
        assert cfg.project == "from-env"
        assert cfg.staging_bucket == "gs://toml-bucket/"

    def test_cli_overrides_env(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GEM_TRANSCRIBE_PROJECT", "from-env")
        monkeypatch.setenv("GEM_TRANSCRIBE_STAGING_BUCKET", "gs://env-bucket/")
        cfg = get_config(project="from-cli")
        assert cfg.project == "from-cli"
        assert cfg.staging_bucket == "gs://env-bucket/"

    def test_empty_overrides_ignored(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GEM_TRANSCRIBE_PROJECT", "real-project")
        monkeypatch.setenv("GEM_TRANSCRIBE_STAGING_BUCKET", "gs://real/")
        cfg = get_config(project="", model=None)
        assert cfg.project == "real-project"

    def test_missing_project_raises(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.delenv("GEM_TRANSCRIBE_PROJECT", raising=False)
        monkeypatch.setenv("GEM_TRANSCRIBE_STAGING_BUCKET", "gs://b/")
        with pytest.raises(ValueError, match="project"):
            get_config(config_path=tmp_path / "missing.toml")

    def test_missing_staging_bucket_raises(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("GEM_TRANSCRIBE_PROJECT", "p")
        monkeypatch.delenv("GEM_TRANSCRIBE_STAGING_BUCKET", raising=False)
        with pytest.raises(ValueError, match="staging_bucket"):
            get_config(config_path=tmp_path / "missing.toml")

    def test_invalid_staging_bucket_scheme_raises(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("GEM_TRANSCRIBE_PROJECT", "p")
        monkeypatch.setenv("GEM_TRANSCRIBE_STAGING_BUCKET", "s3://wrong/")
        with pytest.raises(ValueError, match="gs://"):
            get_config(config_path=tmp_path / "missing.toml")

    def test_default_config_path_used_when_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", Path("/nonexistent/x.toml"))
        monkeypatch.setenv("GEM_TRANSCRIBE_PROJECT", "p")
        monkeypatch.setenv("GEM_TRANSCRIBE_STAGING_BUCKET", "gs://b/")
        cfg = get_config()
        assert isinstance(cfg, Config)
