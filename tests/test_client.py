"""Tests for gem_transcribe.llm.client."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from gem_transcribe.config import Config
from gem_transcribe.llm.client import GeminiClient, _is_retryable, repair_json


def _make_response(text: str | None, finish_reason: object | None = "STOP") -> MagicMock:
    response = MagicMock()
    response.text = text
    candidate = MagicMock()
    candidate.finish_reason = finish_reason
    response.candidates = [candidate]
    return response


@pytest.fixture
def mock_genai_client() -> MagicMock:
    return MagicMock()


@pytest.fixture
def client(sample_config: Config, mock_genai_client: MagicMock) -> GeminiClient:
    return GeminiClient(sample_config, client=mock_genai_client)


class TestIsRetryable:
    @pytest.mark.parametrize(
        "msg",
        [
            "429 Too Many Requests",
            "RESOURCE_EXHAUSTED",
            "rate limit exceeded",
            "Quota exceeded",
            "503 Service Unavailable",
            "service unavailable",
        ],
    )
    def test_retryable(self, msg: str) -> None:
        assert _is_retryable(Exception(msg))

    @pytest.mark.parametrize(
        "msg",
        ["400 Invalid argument", "PERMISSION_DENIED", "NOT_FOUND"],
    )
    def test_non_retryable(self, msg: str) -> None:
        assert not _is_retryable(Exception(msg))


class TestRepairJson:
    def test_passes_through_valid_json(self) -> None:
        s = '{"a": 1}'
        assert repair_json(s) == s

    def test_repairs_trailing_comma(self) -> None:
        repaired = repair_json('{"a": 1,}')
        import json

        assert json.loads(repaired) == {"a": 1}

    def test_unrecoverable_raises(self) -> None:
        with pytest.raises(ValueError, match="could not be repaired"):
            repair_json("this is not json at all !!!")


class TestTranscribe:
    def test_returns_text_on_success(self, client: GeminiClient, mock_genai_client: MagicMock) -> None:
        mock_genai_client.models.generate_content.return_value = _make_response('{"ok": true}')

        out = client.transcribe("gs://b/x.mp3", "prompt")

        assert out == '{"ok": true}'
        call_kwargs = mock_genai_client.models.generate_content.call_args.kwargs
        assert call_kwargs["model"] == "gemini-2.5-flash"
        # contents includes a Part + the prompt string
        assert len(call_kwargs["contents"]) == 2
        assert call_kwargs["contents"][1] == "prompt"

    def test_empty_response_raises(self, client: GeminiClient, mock_genai_client: MagicMock) -> None:
        mock_genai_client.models.generate_content.return_value = _make_response(None, finish_reason="SAFETY")
        with pytest.raises(ValueError, match="empty response"):
            client.transcribe("gs://b/x.mp3", "p")

    def test_truncated_response_raises(self, client: GeminiClient, mock_genai_client: MagicMock) -> None:
        mock_genai_client.models.generate_content.return_value = _make_response("partial", finish_reason="MAX_TOKENS")
        with pytest.raises(ValueError, match="truncated"):
            client.transcribe("gs://b/x.mp3", "p")

    def test_retries_on_rate_limit(
        self,
        client: GeminiClient,
        mock_genai_client: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        sleeps: list[float] = []
        monkeypatch.setattr("gem_transcribe.llm.client.time.sleep", lambda d: sleeps.append(d))

        mock_genai_client.models.generate_content.side_effect = [
            Exception("429 RESOURCE_EXHAUSTED"),
            _make_response('{"ok": true}'),
        ]
        out = client.transcribe("gs://b/x.mp3", "p", max_retries=3)
        assert out == '{"ok": true}'
        assert len(sleeps) == 1

    def test_non_retryable_error_propagates(
        self,
        client: GeminiClient,
        mock_genai_client: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr("gem_transcribe.llm.client.time.sleep", lambda d: None)
        mock_genai_client.models.generate_content.side_effect = Exception("400 invalid argument")
        with pytest.raises(Exception, match="400"):
            client.transcribe("gs://b/x.mp3", "p")

    def test_exhausts_retries(
        self,
        client: GeminiClient,
        mock_genai_client: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr("gem_transcribe.llm.client.time.sleep", lambda d: None)
        mock_genai_client.models.generate_content.side_effect = Exception("429 RESOURCE_EXHAUSTED")
        with pytest.raises(Exception, match="429"):
            client.transcribe("gs://b/x.mp3", "p", max_retries=2)
        assert mock_genai_client.models.generate_content.call_count == 3
