"""Tests for gem_transcribe.cli."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from gem_transcribe.cli import _parse_csv, _per_language_paths, _resolve_basename, main
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

    def test_md_format(
        self,
        sample_transcription: TranscriptionResult,
        cli_env: None,
        tmp_path: Path,
    ) -> None:
        audio = tmp_path / "x.mp3"
        audio.write_bytes(b"x")
        code, out = self._run(sample_transcription, [str(audio), "--format", "md"])
        assert code == 0
        assert "**[00:00:00] Yamada**:" in out

    def test_srt_format_to_stdout(
        self,
        sample_transcription: TranscriptionResult,
        cli_env: None,
        tmp_path: Path,
    ) -> None:
        audio = tmp_path / "x.mp3"
        audio.write_bytes(b"x")
        code, out = self._run(sample_transcription, [str(audio), "--format", "srt"])
        assert code == 0
        assert out.startswith("1\n00:00:00,000 --> 00:00:04,200\n[Yamada]")

    def test_vtt_format_to_stdout(
        self,
        sample_transcription: TranscriptionResult,
        cli_env: None,
        tmp_path: Path,
    ) -> None:
        audio = tmp_path / "x.mp3"
        audio.write_bytes(b"x")
        code, out = self._run(sample_transcription, [str(audio), "--format", "vtt"])
        assert code == 0
        assert out.startswith("WEBVTT")
        assert "<v Yamada>" in out

    def test_srt_output_file_single_language_writes_one_file(
        self,
        cli_env: None,
        tmp_path: Path,
    ) -> None:
        # Use a fixture variant whose result.metadata.languages has exactly one
        # entry so the per-language splitting path is NOT triggered.
        from gem_transcribe.models import Metadata, Segment, TranscriptionResult

        single_lang = TranscriptionResult(
            metadata=Metadata(source="x", model="m", languages=["en"]),
            segments=[
                Segment(start=0.0, end=4.2, speaker="Yamada", text={"en": "Hello."}),
            ],
        )
        audio = tmp_path / "x.mp3"
        audio.write_bytes(b"x")
        out_path = tmp_path / "out.srt"
        code, _ = self._run(
            single_lang,
            [str(audio), "--format", "srt", "--lang", "en", "--output-file", str(out_path)],
        )
        assert code == 0
        # Single-language run writes exactly the requested path
        assert out_path.exists()
        assert "[Yamada]" in out_path.read_text()
        # No per-language siblings created
        assert not (tmp_path / "out.en.srt").exists()

    def test_srt_output_file_multi_language_derives_per_language_paths(
        self,
        sample_transcription: TranscriptionResult,
        cli_env: None,
        tmp_path: Path,
    ) -> None:
        # The shared sample_transcription fixture has metadata.languages = ["en", "ja"]
        audio = tmp_path / "meeting.mp3"
        audio.write_bytes(b"x")
        out_path = tmp_path / "meeting.srt"
        code, _ = self._run(
            sample_transcription,
            [str(audio), "--format", "srt", "--output-file", str(out_path)],
        )
        assert code == 0
        en_path = tmp_path / "meeting.en.srt"
        ja_path = tmp_path / "meeting.ja.srt"
        assert en_path.exists()
        assert ja_path.exists()
        # The bare path is NOT created — only the per-language siblings
        assert not out_path.exists()
        assert "Let's start the meeting." in en_path.read_text()
        assert "会議を始めましょう。" in ja_path.read_text()

    def test_vtt_output_file_multi_language_derives_per_language_paths(
        self,
        sample_transcription: TranscriptionResult,
        cli_env: None,
        tmp_path: Path,
    ) -> None:
        audio = tmp_path / "meeting.mp3"
        audio.write_bytes(b"x")
        out_path = tmp_path / "meeting.vtt"
        code, _ = self._run(
            sample_transcription,
            [str(audio), "--format", "vtt", "--output-file", str(out_path)],
        )
        assert code == 0
        assert (tmp_path / "meeting.en.vtt").exists()
        assert (tmp_path / "meeting.ja.vtt").exists()


class TestProgressReporter:
    """Verify the CLI wires a stderr reporter to ``transcribe`` and that
    ``--quiet`` produces a no-op reporter."""

    def _invoke(
        self,
        sample_transcription: TranscriptionResult,
        audio: Path,
        extra_args: list[str],
    ) -> tuple[int, object]:
        """Run the CLI and return ``(exit_code, transcribe_call_args)``.

        The wired ``reporter`` is exposed via the captured call so each test
        can exercise it independently.
        """
        runner = CliRunner()
        with patch("gem_transcribe.cli.transcribe", return_value=sample_transcription) as mock_t:
            result = runner.invoke(
                main,
                [str(audio), *extra_args],
                catch_exceptions=False,
            )
            return result.exit_code, mock_t.call_args

    def test_default_reporter_writes_to_stderr(
        self,
        sample_transcription: TranscriptionResult,
        cli_env: None,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        audio = tmp_path / "x.mp3"
        audio.write_bytes(b"x")
        code, call_args = self._invoke(sample_transcription, audio, [])
        assert code == 0
        # Exercise the wired reporter directly and confirm it lands on stderr.
        capsys.readouterr()  # drain anything already captured
        call_args.kwargs["reporter"]("hello progress")
        captured = capsys.readouterr()
        assert "hello progress" in captured.err
        assert "hello progress" not in captured.out

    def test_quiet_reporter_is_silent(
        self,
        sample_transcription: TranscriptionResult,
        cli_env: None,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        audio = tmp_path / "x.mp3"
        audio.write_bytes(b"x")
        code, call_args = self._invoke(sample_transcription, audio, ["--quiet"])
        assert code == 0
        capsys.readouterr()
        call_args.kwargs["reporter"]("should not appear")
        captured = capsys.readouterr()
        assert captured.err == ""
        assert captured.out == ""


class TestPerLanguagePaths:
    def test_basic_derivation(self) -> None:
        out = _per_language_paths(Path("/tmp/meeting.srt"), ["en", "ja"], "srt")
        assert out == [
            ("en", Path("/tmp/meeting.en.srt")),
            ("ja", Path("/tmp/meeting.ja.srt")),
        ]

    def test_normalises_extension(self) -> None:
        # User passes --output-file=meeting (no extension)
        out = _per_language_paths(Path("/tmp/meeting"), ["en"], "srt")
        assert out == [("en", Path("/tmp/meeting.en.srt"))]

    def test_replaces_wrong_extension(self) -> None:
        # User passes --output-file=meeting.txt for SRT format
        out = _per_language_paths(Path("/tmp/meeting.txt"), ["en"], "srt")
        assert out == [("en", Path("/tmp/meeting.en.srt"))]

    def test_dedupes_languages(self) -> None:
        out = _per_language_paths(Path("/tmp/m.srt"), ["en", "ja", "en"], "srt")
        # Order preserved, duplicates removed
        assert [lang for lang, _ in out] == ["en", "ja"]
