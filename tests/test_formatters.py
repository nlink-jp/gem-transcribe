"""Tests for gem_transcribe.output.formatters."""

from __future__ import annotations

import json

from gem_transcribe.models import Metadata, Segment, TranscriptionResult
from gem_transcribe.output.formatters import (
    _format_timestamp,
    _pick_text,
    to_json,
    to_text,
)


class TestFormatTimestamp:
    def test_zero(self) -> None:
        assert _format_timestamp(0.0) == "00:00:00.0"

    def test_seconds_and_tenths(self) -> None:
        assert _format_timestamp(1.25) == "00:00:01.2"

    def test_hours(self) -> None:
        assert _format_timestamp(3661.5) == "01:01:01.5"

    def test_negative_clamped(self) -> None:
        assert _format_timestamp(-3.0) == "00:00:00.0"


class TestPickText:
    def test_preferred_language(self) -> None:
        assert _pick_text({"en": "hi", "ja": "はい"}, "en") == "hi"

    def test_fallback_when_preferred_missing(self) -> None:
        assert _pick_text({"ja": "はい"}, "en") == "はい"

    def test_no_preferred_picks_alphabetical_first(self) -> None:
        assert _pick_text({"ja": "はい", "en": "hi"}, None) == "hi"


class TestToJson:
    def test_round_trip(self, sample_transcription: TranscriptionResult) -> None:
        rendered = to_json(sample_transcription)
        loaded = json.loads(rendered)
        assert loaded["metadata"]["model"] == "gemini-2.5-flash"
        assert len(loaded["segments"]) == 2

    def test_indent_default(self, sample_transcription: TranscriptionResult) -> None:
        rendered = to_json(sample_transcription)
        assert "\n  " in rendered  # 2-space indent

    def test_indent_compact(self, sample_transcription: TranscriptionResult) -> None:
        rendered = to_json(sample_transcription, indent=0)
        # indent=0 still inserts newlines but no leading spaces; just check
        # the structure is valid JSON.
        assert json.loads(rendered)["segments"][0]["speaker"] == "Yamada"


class TestToText:
    def test_basic_rendering(self, sample_transcription: TranscriptionResult) -> None:
        rendered = to_text(sample_transcription, language="en")
        lines = rendered.strip().split("\n")
        assert lines[0] == "[00:00:00.0] Yamada: Let's start the meeting."
        assert lines[1] == "[00:00:04.2] Sato: Sounds good."

    def test_japanese_rendering(self, sample_transcription: TranscriptionResult) -> None:
        rendered = to_text(sample_transcription, language="ja")
        assert "会議を始めましょう。" in rendered
        assert "いいですね。" in rendered

    def test_language_default_uses_first_in_metadata(self, sample_transcription: TranscriptionResult) -> None:
        # metadata.languages = ["en", "ja"], so default is en
        rendered = to_text(sample_transcription)
        assert "Let's start the meeting." in rendered

    def test_empty_segments_produces_empty_string(self) -> None:
        result = TranscriptionResult(
            metadata=Metadata(source="x", model="m", languages=["en"]),
            segments=[],
        )
        assert to_text(result) == ""

    def test_missing_preferred_language_falls_back(self) -> None:
        result = TranscriptionResult(
            metadata=Metadata(source="x", model="m", languages=["en"]),
            segments=[
                Segment(start=0, end=1, speaker="A", text={"ja": "はい"}),
            ],
        )
        rendered = to_text(result, language="en")
        assert "はい" in rendered
