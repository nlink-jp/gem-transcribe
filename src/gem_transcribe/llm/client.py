"""Vertex AI Gemini client for transcription."""

from __future__ import annotations

import json
import logging
import time

from google import genai
from google.genai import types
from nlk import backoff
from nlk.jsonfix import JsonFixError
from nlk.jsonfix import extract as jsonfix_extract

from gem_transcribe.config import Config
from gem_transcribe.gcs.uploader import guess_audio_mime
from gem_transcribe.llm.prompts import SYSTEM_INSTRUCTION

logger = logging.getLogger(__name__)

_RETRYABLE_KEYWORDS = ("429", "resource_exhausted", "rate limit", "quota", "503", "unavailable")


def _is_retryable(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(k in msg for k in _RETRYABLE_KEYWORDS)


class GeminiClient:
    """Wrapper around the google-genai SDK in Vertex AI mode."""

    def __init__(self, config: Config, *, client: genai.Client | None = None) -> None:
        self._config = config
        self._client = client or genai.Client(
            vertexai=True,
            project=config.project,
            location=config.location,
        )

    def transcribe(
        self,
        audio_uri: str,
        user_prompt: str,
        *,
        max_retries: int = 5,
    ) -> str:
        """Send the audio + prompt to Gemini and return raw text response.

        Retries on rate-limit / unavailable errors using ``nlk.backoff``.
        Returns the raw model text — JSON parsing is the caller's job
        (the orchestrator handles ``jsonfix`` repair so this method stays
        free of structural assumptions).
        """
        contents: list = [
            types.Part.from_uri(file_uri=audio_uri, mime_type=guess_audio_mime(audio_uri)),
            user_prompt,
        ]
        gen_config = types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            temperature=0.2,
            max_output_tokens=self._config.max_output_tokens,
            response_mime_type="application/json",
        )

        last_error: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                response = self._client.models.generate_content(
                    model=self._config.model,
                    contents=contents,
                    config=gen_config,
                )
                text = response.text
                if not text:
                    finish_reason = _safe_finish_reason(response)
                    raise ValueError(
                        f"Gemini returned an empty response (finish_reason={finish_reason}). "
                        "Possible causes: safety filter, content policy block, or quota issue."
                    )
                finish_reason = _safe_finish_reason(response)
                if finish_reason and str(finish_reason).upper() in (
                    "MAX_TOKENS",
                    "FINISH_REASON_MAX_TOKENS",
                ):
                    raise ValueError(
                        f"Gemini response was truncated (finish_reason={finish_reason}). "
                        f"Output exceeded max_output_tokens={self._config.max_output_tokens}. "
                        "Increase GEM_TRANSCRIBE_MAX_OUTPUT_TOKENS or split the audio."
                    )
                return text
            except Exception as exc:
                if not _is_retryable(exc) or attempt == max_retries:
                    raise
                last_error = exc
                delay = backoff.duration(attempt)
                logger.warning(
                    "Vertex AI rate limited (attempt %d/%d), retrying in %.1fs: %s",
                    attempt + 1,
                    max_retries + 1,
                    delay,
                    exc,
                )
                time.sleep(delay)

        # Unreachable: the loop either returns or re-raises on the last attempt.
        raise last_error  # type: ignore[misc]


def _safe_finish_reason(response) -> object | None:
    try:
        return response.candidates[0].finish_reason
    except (AttributeError, IndexError, TypeError):
        return None


def repair_json(raw: str) -> str:
    """Validate JSON, repairing via ``nlk.jsonfix`` if necessary.

    Returns a string that is guaranteed to be parseable by ``json.loads``.
    Raises ``ValueError`` if the response is unrecoverable.
    """
    try:
        json.loads(raw)
        return raw
    except json.JSONDecodeError as exc:
        logger.warning(
            "Gemini returned malformed JSON (%s, len=%d), attempting repair...",
            exc,
            len(raw),
        )
        try:
            repaired = jsonfix_extract(raw)
            json.loads(repaired)
            logger.info("JSON repair successful.")
            return repaired
        except (JsonFixError, json.JSONDecodeError) as inner:
            raise ValueError(
                f"Gemini returned JSON that could not be repaired ({exc}). Response length: {len(raw)} chars."
            ) from inner
