"""Shared test fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from gem_transcribe.config import Config
from gem_transcribe.models import Metadata, Segment, TranscriptionResult


@pytest.fixture
def sample_config() -> Config:
    return Config(
        project="test-project",
        location="us-central1",
        model="gemini-2.5-flash",
        staging_bucket="gs://test-bucket/gem-transcribe/",
        keep_staging=False,
        default_languages=["en"],
        request_timeout=1800,
    )


@pytest.fixture
def sample_transcription() -> TranscriptionResult:
    return TranscriptionResult(
        metadata=Metadata(
            source="test.mp3",
            model="gemini-2.5-flash",
            duration_seconds=12.5,
            languages=["en", "ja"],
            speaker_hints=["Yamada", "Sato"],
        ),
        segments=[
            Segment(
                start=0.0,
                end=4.2,
                speaker="Yamada",
                text={"en": "Let's start the meeting.", "ja": "会議を始めましょう。"},
            ),
            Segment(
                start=4.2,
                end=10.0,
                speaker="Sato",
                text={"en": "Sounds good.", "ja": "いいですね。"},
            ),
        ],
    )


@pytest.fixture
def isolated_config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolate ~/.config/gem-transcribe/ to avoid leaking the user's real config."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr("pathlib.Path.home", lambda: home)
    return home
