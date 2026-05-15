"""Tests for gem_transcribe.cli."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from gem_transcribe.cli import _parse_csv, _resolve_basename, main
from gem_transcribe.models import TranscriptionResult


class TestParseCsv:
    def test_none_input(self) -> None:
        assert _parse_csv(None) is None

    def test_empty_string(self) -> None:
        assert _parse_csv("") is None

    def test_single(self) -> None:
        assert _parse_csv("en") == ["en"]

    def test_csv(self) -> None:
        assert _parse_csv("en, ja , de") == ["en", "ja", "de"]

    def test_only_separators_returns_none(self) -> None:
        assert _parse_csv(", ,") is None


class TestResolveBasename:
    def test_local_path(self) -> None:
        assert _resolve_basename("/foo/bar/meeting.mp3") == "meeting"

    def test_gs_uri(self) -> None:
        assert _resolve_basename("gs://b/a/b/c/recording.wav") == "recording"

    def test_no_extension(self) -> None:
        assert _resolve_basename("/foo/bar") == "bar"


@pytest.fixture
def cli_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEM_TRANSCRIBE_PROJECT", "p")
    monkeypatch.setenv("GEM_TRANSCRIBE_STAGING_BUCKET", "gs://b/")


class TestMain:
    def _run(
        self,
        sample_transcription: TranscriptionResult,
        args: list[str],
    ) -> "tuple[int, str]":
        runner = CliRunner()
        with patch("gem_transcribe.cli.transcribe", return_value=sample_transcription) as mock_t:
            result = runner.invoke(main, args, catch_exceptions=False)
            self.last_call = mock_t.call_args
        return result.exit_code, result.output

    def test_default_outputs_json_to_stdout(
        self,
        sample_transcription: TranscriptionResult,
        cli_env: None,
        tmp_path: Path,
    ) -> None:
        audio = tmp_path / "x.mp3"
        audio.write_bytes(b"x")
        code, out = self._run(sample_transcription, [str(audio)])
        assert code == 0
        # Output mixes stdout (JSON) and stderr (none in default verbosity).
        # The first JSON object on output is what we wrote.
        loaded = json.loads(out)
        assert loaded["metadata"]["model"] == "gemini-2.5-flash"

    def test_text_format(
        self,
        sample_transcription: TranscriptionResult,
        cli_env: None,
        tmp_path: Path,
    ) -> None:
        audio = tmp_path / "x.mp3"
        audio.write_bytes(b"x")
        code, out = self._run(sample_transcription, [str(audio), "--format", "text"])
        assert code == 0
        assert "Yamada" in out
        assert "Sato" in out

    def test_output_file(
        self,
        sample_transcription: TranscriptionResult,
        cli_env: None,
        tmp_path: Path,
    ) -> None:
        audio = tmp_path / "x.mp3"
        audio.write_bytes(b"x")
        out_path = tmp_path / "out.json"
        code, _ = self._run(sample_transcription, [str(audio), "--output-file", str(out_path)])
        assert code == 0
        assert out_path.exists()
        loaded = json.loads(out_path.read_text())
        assert "segments" in loaded

    def test_output_dir_emits_both(
        self,
        sample_transcription: TranscriptionResult,
        cli_env: None,
        tmp_path: Path,
    ) -> None:
        audio = tmp_path / "meeting.mp3"
        audio.write_bytes(b"x")
        out_dir = tmp_path / "out"
        code, _ = self._run(sample_transcription, [str(audio), "--output-dir", str(out_dir)])
        assert code == 0
        assert (out_dir / "meeting.json").exists()
        assert (out_dir / "meeting.txt").exists()

    def test_output_file_and_dir_conflict(
        self,
        sample_transcription: TranscriptionResult,
        cli_env: None,
        tmp_path: Path,
    ) -> None:
        audio = tmp_path / "x.mp3"
        audio.write_bytes(b"x")
        runner = CliRunner()
        result = runner.invoke(
            main,
            [str(audio), "--output-file", "/tmp/x.json", "--output-dir", "/tmp/d"],
        )
        assert result.exit_code != 0
        assert "mutually exclusive" in result.output

    def test_csv_flags_passed_to_transcribe(
        self,
        sample_transcription: TranscriptionResult,
        cli_env: None,
        tmp_path: Path,
    ) -> None:
        audio = tmp_path / "x.mp3"
        audio.write_bytes(b"x")
        self._run(
            sample_transcription,
            [str(audio), "--lang", "en,ja", "--speaker-hint", "Yamada,Sato"],
        )
        kwargs = self.last_call.kwargs
        assert kwargs["languages"] == ["en", "ja"]
        assert kwargs["speaker_hints"] == ["Yamada", "Sato"]

    def test_missing_config_surfaces_usage_error(
        self,
        sample_transcription: TranscriptionResult,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        monkeypatch.delenv("GEM_TRANSCRIBE_PROJECT", raising=False)
        monkeypatch.delenv("GEM_TRANSCRIBE_STAGING_BUCKET", raising=False)
        runner = CliRunner()
        result = runner.invoke(
            main,
            [str(tmp_path / "x.mp3"), "--config", str(tmp_path / "missing.toml")],
        )
        assert result.exit_code != 0
        assert "Missing required configuration" in result.output
