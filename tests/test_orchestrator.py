"""Tests for gem_transcribe.orchestrator."""

from __future__ import annotations

import json
from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest

from gem_transcribe.config import Config
from gem_transcribe.models import TranscriptionResult
from gem_transcribe.orchestrator import _build_result, _normalise_timestamps, transcribe


def _model_payload() -> dict:
    return {
        "metadata": {"duration_seconds": 10.5},
        "segments": [
            {
                "start": 0.0,
                "end": 4.0,
                "speaker": "Speaker A",
                "text": {"en": "Hello there."},
            },
            {
                "start": 4.0,
                "end": 9.0,
                "speaker": "Speaker B",
                "text": {"en": "General Kenobi."},
            },
        ],
    }


@pytest.fixture
def fake_uploader() -> MagicMock:
    u = MagicMock()

    @contextmanager
    def staged(input_arg: str):
        if input_arg.startswith("gs://"):
            yield input_arg
        else:
            yield "gs://test-bucket/staged/abc.mp3"

    u.staged.side_effect = staged
    return u


@pytest.fixture
def fake_client() -> MagicMock:
    c = MagicMock()
    c.transcribe.return_value = json.dumps(_model_payload())
    return c


class TestTranscribe:
    def test_happy_path_local_file(
        self, sample_config: Config, fake_uploader: MagicMock, fake_client: MagicMock
    ) -> None:
        result = transcribe(
            "/local/meeting.mp3",
            config=sample_config,
            languages=["en"],
            speaker_hints=None,
            uploader=fake_uploader,
            client=fake_client,
        )

        assert isinstance(result, TranscriptionResult)
        assert result.metadata.source == "/local/meeting.mp3"
        assert result.metadata.model == "gemini-2.5-flash"
        assert result.metadata.languages == ["en"]
        assert result.metadata.speaker_hints == []
        assert result.metadata.duration_seconds == 10.5
        assert len(result.segments) == 2
        assert result.segments[0].speaker == "Speaker A"

    def test_passes_through_gs_uri(
        self, sample_config: Config, fake_uploader: MagicMock, fake_client: MagicMock
    ) -> None:
        result = transcribe(
            "gs://other-bucket/foo.mp3",
            config=sample_config,
            uploader=fake_uploader,
            client=fake_client,
        )
        # The Gemini client receives the original URI, not a re-staged one
        fake_client.transcribe.assert_called_once()
        assert fake_client.transcribe.call_args.args[0] == "gs://other-bucket/foo.mp3"
        assert result.metadata.source == "gs://other-bucket/foo.mp3"

    def test_default_languages_used_when_none(
        self, sample_config: Config, fake_uploader: MagicMock, fake_client: MagicMock
    ) -> None:
        cfg = sample_config.model_copy(update={"default_languages": ["ja"]})
        # The model returns en in the canned payload; build a ja payload instead
        fake_client.transcribe.return_value = json.dumps(
            {"segments": [{"start": 0, "end": 1, "speaker": "A", "text": {"ja": "はい"}}]}
        )
        result = transcribe(
            "/local/x.mp3",
            config=cfg,
            uploader=fake_uploader,
            client=fake_client,
        )
        assert result.metadata.languages == ["ja"]

    def test_speaker_hints_propagated_to_metadata(
        self, sample_config: Config, fake_uploader: MagicMock, fake_client: MagicMock
    ) -> None:
        result = transcribe(
            "/local/x.mp3",
            config=sample_config,
            languages=["en"],
            speaker_hints=["Yamada", "Sato"],
            uploader=fake_uploader,
            client=fake_client,
        )
        assert result.metadata.speaker_hints == ["Yamada", "Sato"]

    def test_invalid_json_raises_value_error(
        self, sample_config: Config, fake_uploader: MagicMock, fake_client: MagicMock
    ) -> None:
        fake_client.transcribe.return_value = "not json at all !!!"
        with pytest.raises(ValueError, match="could not be repaired"):
            transcribe(
                "/local/x.mp3",
                config=sample_config,
                uploader=fake_uploader,
                client=fake_client,
            )


class TestNormaliseTimestamps:
    def test_passes_through_valid_segments(self) -> None:
        segs = [{"start": 0.0, "end": 4.0}, {"start": 4.0, "end": 8.0}]
        assert _normalise_timestamps(segs) == segs

    def test_rewrites_end_when_smaller_than_start(self) -> None:
        segs = [{"start": 10.0, "end": 2.5}]
        out = _normalise_timestamps(segs)
        assert out[0]["end"] == pytest.approx(12.5)
        # Original input not mutated
        assert segs[0]["end"] == 2.5

    def test_skips_repair_when_end_already_valid(self) -> None:
        segs = [{"start": 0.0, "end": 0.0}]  # end == start, not < start
        assert _normalise_timestamps(segs) == segs

    def test_handles_negative_end_unchanged(self) -> None:
        # Negative ends are not duration-style; leave them so validation rejects
        segs = [{"start": 1.0, "end": -1.0}]
        assert _normalise_timestamps(segs) == segs

    def test_non_dict_entries_passed_through(self) -> None:
        # Pydantic will reject these, but normalisation must not crash
        segs = ["not a dict"]
        assert _normalise_timestamps(segs) == segs


class TestBuildResult:
    def test_rejects_non_object_payload(self) -> None:
        with pytest.raises(ValueError, match="object"):
            _build_result(
                ["not", "a", "dict"],  # type: ignore[arg-type]
                source="x",
                model="m",
                languages=["en"],
                speaker_hints=[],
            )

    def test_rejects_missing_segments(self) -> None:
        with pytest.raises(ValueError, match="segments"):
            _build_result(
                {"metadata": {}},
                source="x",
                model="m",
                languages=["en"],
                speaker_hints=[],
            )

    def test_invalid_segment_raises(self) -> None:
        # Missing speaker — duration repair won't help, so validation must fail.
        bad = {"segments": [{"start": 0, "end": 1, "text": {"en": "x"}}]}
        with pytest.raises(ValueError, match="invalid segment"):
            _build_result(bad, source="x", model="m", languages=["en"], speaker_hints=[])

    def test_repairs_duration_style_end_values(self) -> None:
        # The Gemini quirk: end emitted as duration relative to start
        bad = {
            "segments": [
                {"start": 0.0, "end": 4.2, "speaker": "A", "text": {"en": "Hi"}},
                {"start": 4.2, "end": 1.0, "speaker": "B", "text": {"en": "Yo"}},
            ]
        }
        result = _build_result(bad, source="x", model="m", languages=["en"], speaker_hints=[])
        # Second segment's end should be repaired: 4.2 + 1.0 = 5.2
        assert result.segments[1].end == pytest.approx(5.2)

    def test_metadata_overridden_by_invocation(self) -> None:
        payload = {
            "metadata": {
                "source": "fake-source-from-llm",
                "duration_seconds": 7.5,
            },
            "segments": [{"start": 0, "end": 1, "speaker": "A", "text": {"en": "x"}}],
        }
        result = _build_result(
            payload,
            source="real-source.mp3",
            model="real-model",
            languages=["en"],
            speaker_hints=["foo"],
        )
        # Source/model come from the invocation, not the LLM
        assert result.metadata.source == "real-source.mp3"
        assert result.metadata.model == "real-model"
        # duration_seconds is taken from the LLM payload
        assert result.metadata.duration_seconds == 7.5
