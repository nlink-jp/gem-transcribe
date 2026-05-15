"""Tests for gem_transcribe.output.formatters."""

from __future__ import annotations

import json

from gem_transcribe.models import Metadata, Segment, TranscriptionResult
from gem_transcribe.output.formatters import (
    _escape_vtt_text,
    _format_srt_timestamp,
    _format_timestamp,
    _format_timestamp_seconds,
    _format_vtt_timestamp,
    _pick_text,
    _sanitize_srt_text,
    to_json,
    to_markdown,
    to_srt,
    to_text,
    to_vtt,
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


class TestSubtitleTimestamps:
    def test_srt_separator_is_comma(self) -> None:
        assert _format_srt_timestamp(0.0) == "00:00:00,000"
        assert _format_srt_timestamp(1.234) == "00:00:01,234"

    def test_vtt_separator_is_period(self) -> None:
        assert _format_vtt_timestamp(0.0) == "00:00:00.000"
        assert _format_vtt_timestamp(1.234) == "00:00:01.234"

    def test_hour_rollover(self) -> None:
        assert _format_srt_timestamp(3661.5) == "01:01:01,500"
        assert _format_vtt_timestamp(3661.5) == "01:01:01.500"

    def test_negative_clamped_to_zero(self) -> None:
        assert _format_srt_timestamp(-1.0) == "00:00:00,000"
        assert _format_vtt_timestamp(-1.0) == "00:00:00.000"

    def test_format_timestamp_seconds_truncates_subsecond(self) -> None:
        assert _format_timestamp_seconds(0.0) == "00:00:00"
        assert _format_timestamp_seconds(1.7) == "00:00:02"  # rounded
        assert _format_timestamp_seconds(3661.4) == "01:01:01"


class TestSanitisers:
    def test_srt_replaces_arrow(self) -> None:
        assert _sanitize_srt_text("a --> b") == "a → b"

    def test_srt_collapses_blank_lines(self) -> None:
        assert _sanitize_srt_text("a\n\n\nb") == "a\nb"

    def test_vtt_escapes_html_entities(self) -> None:
        assert _escape_vtt_text("<v fake>&hi") == "&lt;v fake&gt;&amp;hi"

    def test_vtt_replaces_arrow(self) -> None:
        assert "-->" not in _escape_vtt_text("a --> b")
        assert "→" in _escape_vtt_text("a --> b")


class TestToMarkdown:
    def test_basic_rendering(self, sample_transcription: TranscriptionResult) -> None:
        rendered = to_markdown(sample_transcription, language="en")
        assert "**[00:00:00] Yamada**: Let's start the meeting." in rendered
        assert "**[00:00:04] Sato**: Sounds good." in rendered

    def test_japanese_rendering(self, sample_transcription: TranscriptionResult) -> None:
        rendered = to_markdown(sample_transcription, language="ja")
        assert "会議を始めましょう。" in rendered

    def test_default_language_uses_first(self, sample_transcription: TranscriptionResult) -> None:
        rendered = to_markdown(sample_transcription)
        # metadata.languages = ["en", "ja"]
        assert "Let's start the meeting." in rendered

    def test_empty_segments_produces_empty_string(self) -> None:
        result = TranscriptionResult(
            metadata=Metadata(source="x", model="m", languages=["en"]),
            segments=[],
        )
        assert to_markdown(result) == ""

    def test_collapses_multiline_text(self) -> None:
        result = TranscriptionResult(
            metadata=Metadata(source="x", model="m", languages=["en"]),
            segments=[
                Segment(start=0, end=1, speaker="A", text={"en": "Line one\nLine two"}),
            ],
        )
        rendered = to_markdown(result)
        # Each segment must remain a single line in Markdown timeline mode
        assert rendered.count("\n") <= 1
        assert "Line one Line two" in rendered


class TestToSrt:
    def test_basic_rendering(self, sample_transcription: TranscriptionResult) -> None:
        rendered = to_srt(sample_transcription, language="en")
        # First cue
        assert rendered.startswith("1\n00:00:00,000 --> 00:00:04,200\n[Yamada] Let's start the meeting.\n")
        # Second cue
        assert "2\n00:00:04,200 --> 00:00:10,000\n[Sato] Sounds good.\n" in rendered

    def test_cue_separation_is_blank_line(self, sample_transcription: TranscriptionResult) -> None:
        rendered = to_srt(sample_transcription, language="en")
        assert "\n\n" in rendered

    def test_japanese_rendering(self, sample_transcription: TranscriptionResult) -> None:
        rendered = to_srt(sample_transcription, language="ja")
        assert "[Yamada] 会議を始めましょう。" in rendered

    def test_empty_segments_produces_empty_string(self) -> None:
        result = TranscriptionResult(
            metadata=Metadata(source="x", model="m", languages=["en"]),
            segments=[],
        )
        assert to_srt(result) == ""

    def test_text_with_arrow_is_sanitised(self) -> None:
        result = TranscriptionResult(
            metadata=Metadata(source="x", model="m", languages=["en"]),
            segments=[
                Segment(start=0, end=1, speaker="A", text={"en": "before --> after"}),
            ],
        )
        rendered = to_srt(result)
        # The literal --> arrow appears once (the cue timestamp); no double instance
        assert rendered.count("-->") == 1
        assert "before → after" in rendered


class TestToVtt:
    def test_starts_with_webvtt_header(self, sample_transcription: TranscriptionResult) -> None:
        rendered = to_vtt(sample_transcription, language="en")
        assert rendered.startswith("WEBVTT\n")

    def test_uses_voice_tag(self, sample_transcription: TranscriptionResult) -> None:
        rendered = to_vtt(sample_transcription, language="en")
        assert "<v Yamada>Let's start the meeting." in rendered
        assert "<v Sato>Sounds good." in rendered

    def test_period_separator_in_timestamps(self, sample_transcription: TranscriptionResult) -> None:
        rendered = to_vtt(sample_transcription, language="en")
        assert "00:00:00.000 --> 00:00:04.200" in rendered

    def test_empty_segments_produces_only_header(self) -> None:
        result = TranscriptionResult(
            metadata=Metadata(source="x", model="m", languages=["en"]),
            segments=[],
        )
        rendered = to_vtt(result)
        assert rendered == "WEBVTT\n"

    def test_html_entities_escaped(self) -> None:
        result = TranscriptionResult(
            metadata=Metadata(source="x", model="m", languages=["en"]),
            segments=[
                Segment(start=0, end=1, speaker="A&B", text={"en": "<script>"}),
            ],
        )
        rendered = to_vtt(result)
        assert "<v A&amp;B>&lt;script&gt;" in rendered
