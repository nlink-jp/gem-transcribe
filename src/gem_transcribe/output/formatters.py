"""Output formatters for transcription results."""

from __future__ import annotations

from gem_transcribe.models import TranscriptionResult


def to_json(result: TranscriptionResult, *, indent: int = 2) -> str:
    """Serialize as pretty-printed JSON."""
    return result.model_dump_json(indent=indent)


def to_text(result: TranscriptionResult, *, language: str | None = None) -> str:
    """Render as human-readable plain text.

    Lines look like::

        [00:00:01.2] Speaker A: Hello there.

    Args:
        result: The transcription result to render.
        language: Which language key to render. Defaults to the first
            language in ``result.metadata.languages``. If the chosen language
            is missing for a segment the first available text is used (so
            callers always get *some* output rather than empty lines).
    """
    chosen = language or (result.metadata.languages[0] if result.metadata.languages else None)
    lines: list[str] = []
    for seg in result.segments:
        ts = _format_timestamp(seg.start)
        text = _pick_text(seg.text, chosen)
        lines.append(f"[{ts}] {seg.speaker}: {text}")
    return "\n".join(lines) + ("\n" if lines else "")


def _format_timestamp(seconds: float) -> str:
    if seconds < 0:
        seconds = 0.0
    total_ms = int(round(seconds * 1000))
    h, rem_ms = divmod(total_ms, 3_600_000)
    m, rem_ms = divmod(rem_ms, 60_000)
    s, ms = divmod(rem_ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms // 100}"


def _pick_text(text: dict[str, str], preferred: str | None) -> str:
    if preferred and preferred in text:
        return text[preferred]
    # Fall back to whichever language is available (deterministic order).
    for key in sorted(text.keys()):
        return text[key]
    return ""
