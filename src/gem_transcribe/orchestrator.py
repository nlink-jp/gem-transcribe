"""End-to-end transcription orchestration."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable, Sequence
from pathlib import Path

from pydantic import ValidationError

from gem_transcribe.config import Config
from gem_transcribe.gcs.uploader import StagingUploader, is_gcs_uri
from gem_transcribe.llm.client import GeminiClient, repair_json
from gem_transcribe.llm.prompts import build_user_prompt
from gem_transcribe.models import Metadata, Segment, TranscriptionResult

logger = logging.getLogger(__name__)

Reporter = Callable[[str], None]


def _noop_reporter(_: str) -> None:
    pass


def _format_elapsed(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes}m{secs:02d}s"


def transcribe(
    input_arg: str,
    *,
    config: Config,
    languages: Sequence[str] | None = None,
    speaker_hints: Sequence[str] | None = None,
    uploader: StagingUploader | None = None,
    client: GeminiClient | None = None,
    reporter: Reporter = _noop_reporter,
) -> TranscriptionResult:
    """Transcribe a single audio source end-to-end.

    Args:
        input_arg: Local file path or ``gs://`` URI.
        config: Loaded configuration.
        languages: Output languages. Falls back to ``config.default_languages``
            when ``None`` or empty.
        speaker_hints: Optional list of participant names for attribution.
        uploader: Override the default ``StagingUploader`` (for testing).
        client: Override the default ``GeminiClient`` (for testing).
        reporter: One-line progress sink called at each milestone (upload,
            transcribe start, transcribe done with elapsed). Defaults to a
            no-op so library use stays silent; the CLI wires this to stderr.

    Returns:
        A validated ``TranscriptionResult``.
    """
    langs = list(languages) if languages else list(config.default_languages)
    if not langs:
        raise ValueError("at least one output language is required")

    hints = list(speaker_hints) if speaker_hints else []
    uploader = uploader or StagingUploader(config)
    client = client or GeminiClient(config)
    user_prompt = build_user_prompt(languages=langs, speaker_hints=hints or None)

    is_local = not is_gcs_uri(input_arg)
    if is_local:
        reporter(f"Uploading {Path(input_arg).name} to GCS staging...")

    with uploader.staged(input_arg) as gs_uri:
        logger.info("Transcribing %s (model=%s, languages=%s)", gs_uri, config.model, langs)
        reporter(f"Transcribing with {config.model} (languages={','.join(langs)}); this may take several minutes...")
        start = time.monotonic()
        raw = client.transcribe(gs_uri, user_prompt)
        reporter(f"Transcription complete in {_format_elapsed(time.monotonic() - start)}")

    if is_local and not config.keep_staging:
        reporter("Cleaned up staging object")

    repaired = repair_json(raw)
    payload = json.loads(repaired)
    return _build_result(
        payload,
        source=input_arg,
        model=config.model,
        languages=langs,
        speaker_hints=hints,
    )


def _build_result(
    payload: dict,
    *,
    source: str,
    model: str,
    languages: list[str],
    speaker_hints: list[str],
) -> TranscriptionResult:
    """Convert the LLM JSON payload into a ``TranscriptionResult``.

    The model is asked to produce ``{"metadata": {"duration_seconds": ...},
    "segments": [...]}``. We rebuild ``metadata`` ourselves so that
    ``source``, ``model``, ``languages`` and ``speaker_hints`` come from the
    invocation rather than the model — preventing tampering and making the
    output reproducible.
    """
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object from model, got {type(payload).__name__}")
    raw_segments = payload.get("segments")
    if not isinstance(raw_segments, list):
        raise ValueError("model response missing 'segments' array")

    duration: float | None = None
    raw_meta = payload.get("metadata")
    if isinstance(raw_meta, dict):
        ds = raw_meta.get("duration_seconds")
        if isinstance(ds, (int, float)):
            duration = float(ds)

    normalised = _normalise_timestamps(raw_segments)

    try:
        segments = [Segment.model_validate(s) for s in normalised]
    except ValidationError as exc:
        raise ValueError(f"model produced invalid segment data: {exc}") from exc

    return TranscriptionResult(
        metadata=Metadata(
            source=source,
            model=model,
            duration_seconds=duration,
            languages=languages,
            speaker_hints=speaker_hints,
        ),
        segments=segments,
    )


def _normalise_timestamps(raw_segments: list) -> list:
    """Repair common timestamp quirks from the model.

    Despite the prompt's instructions, Gemini occasionally emits ``end`` as a
    duration rather than an absolute timestamp (e.g. ``start=59.96, end=1.0``
    meaning "1 second long, ending at 60.96"). When we detect this, we
    interpret ``end`` as a duration and rewrite it to ``start + end``.
    A warning is logged so the issue is visible in --verbose runs.
    """
    repaired: list = []
    fix_count = 0
    for seg in raw_segments:
        if not isinstance(seg, dict):
            repaired.append(seg)
            continue
        start = seg.get("start")
        end = seg.get("end")
        if isinstance(start, (int, float)) and isinstance(end, (int, float)) and end < start and end >= 0:
            new = dict(seg)
            new["end"] = float(start) + float(end)
            repaired.append(new)
            fix_count += 1
        else:
            repaired.append(seg)
    if fix_count:
        logger.warning(
            "Re-interpreted %d/%d segment 'end' values as durations "
            "(model emitted relative offsets despite the absolute-timestamp instruction).",
            fix_count,
            len(raw_segments),
        )
    return repaired
