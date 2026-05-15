"""Tests for gem_transcribe.models."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from gem_transcribe.models import Metadata, Segment, TranscriptionResult


class TestSegment:
    def test_valid_segment(self) -> None:
        s = Segment(start=0.0, end=4.2, speaker="Speaker A", text={"en": "Hi"})
        assert s.speaker == "Speaker A"
        assert s.text == {"en": "Hi"}

    def test_end_before_start_rejected(self) -> None:
        with pytest.raises(ValidationError, match="end"):
            Segment(start=5.0, end=3.0, speaker="A", text={"en": "x"})

    def test_negative_start_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Segment(start=-0.1, end=1.0, speaker="A", text={"en": "x"})

    def test_empty_speaker_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Segment(start=0.0, end=1.0, speaker="", text={"en": "x"})

    def test_empty_text_dict_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Segment(start=0.0, end=1.0, speaker="A", text={})

    def test_blank_text_value_rejected(self) -> None:
        with pytest.raises(ValidationError, match="non-empty"):
            Segment(start=0.0, end=1.0, speaker="A", text={"en": "   "})

    def test_multilingual_text(self) -> None:
        s = Segment(start=0.0, end=1.0, speaker="A", text={"en": "Hi", "ja": "はい"})
        assert set(s.text.keys()) == {"en", "ja"}


class TestMetadata:
    def test_required_fields(self) -> None:
        m = Metadata(source="x.mp3", model="gemini-2.5-flash", languages=["en"])
        assert m.speaker_hints == []
        assert m.duration_seconds is None

    def test_languages_required(self) -> None:
        with pytest.raises(ValidationError):
            Metadata(source="x.mp3", model="m", languages=[])


class TestTranscriptionResult:
    def test_full_construction(self, sample_transcription: TranscriptionResult) -> None:
        assert len(sample_transcription.segments) == 2
        assert sample_transcription.metadata.languages == ["en", "ja"]

    def test_json_round_trip(self, sample_transcription: TranscriptionResult) -> None:
        raw = sample_transcription.model_dump_json()
        loaded = TranscriptionResult.model_validate_json(raw)
        assert loaded == sample_transcription

    def test_json_structure(self, sample_transcription: TranscriptionResult) -> None:
        data = json.loads(sample_transcription.model_dump_json())
        assert "metadata" in data
        assert "segments" in data
        assert data["segments"][0]["text"]["en"] == "Let's start the meeting."
