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
    chosen = _resolve_language(result, language)
    lines: list[str] = []
    for seg in result.segments:
        ts = _format_timestamp(seg.start)
        text = _pick_text(seg.text, chosen)
        lines.append(f"[{ts}] {seg.speaker}: {text}")
    return "\n".join(lines) + ("\n" if lines else "")


def to_markdown(result: TranscriptionResult, *, language: str | None = None) -> str:
    """Render as a Markdown timeline, one line per segment.

    Each line uses the form ``**[hh:mm:ss] Speaker**: text`` so the speaker
    label and timestamp are visually anchored when rendered.
    """
    chosen = _resolve_language(result, language)
    lines: list[str] = []
    for seg in result.segments:
        ts = _format_timestamp_seconds(seg.start)
        text = _pick_text(seg.text, chosen)
        # Collapse newlines so the line stays a single Markdown bullet.
        text_one_line = " ".join(text.splitlines()).strip()
        lines.append(f"**[{ts}] {seg.speaker}**: {text_one_line}")
    return "\n\n".join(lines) + ("\n" if lines else "")


def to_srt(result: TranscriptionResult, *, language: str | None = None) -> str:
    """Render as SubRip (SRT) subtitles.

    Each segment becomes one cue with the speaker name as a bracketed
    prefix on the first line. Multi-line speaker text is preserved.
    Empty input produces an empty string.
    """
    chosen = _resolve_language(result, language)
    cues: list[str] = []
    for index, seg in enumerate(result.segments, start=1):
        start = _format_srt_timestamp(seg.start)
        end = _format_srt_timestamp(seg.end)
        text = _sanitize_srt_text(_pick_text(seg.text, chosen))
        body = f"[{seg.speaker}] {text}" if seg.speaker else text
        cues.append(f"{index}\n{start} --> {end}\n{body}\n")
    return "\n".join(cues)


def to_vtt(result: TranscriptionResult, *, language: str | None = None) -> str:
    """Render as WebVTT.

    Speaker is encoded with the WebVTT voice tag (``<v Name>text``) so that
    compliant players can style or filter by speaker.
    """
    chosen = _resolve_language(result, language)
    parts: list[str] = ["WEBVTT", ""]
    for seg in result.segments:
        start = _format_vtt_timestamp(seg.start)
        end = _format_vtt_timestamp(seg.end)
        text = _escape_vtt_text(_pick_text(seg.text, chosen))
        if seg.speaker:
            speaker = _escape_vtt_text(seg.speaker)
            body = f"<v {speaker}>{text}"
        else:
            body = text
        parts.append(f"{start} --> {end}\n{body}\n")
    return "\n".join(parts).rstrip("\n") + "\n"


def _resolve_language(result: TranscriptionResult, language: str | None) -> str | None:
    if language:
        return language
    return result.metadata.languages[0] if result.metadata.languages else None


def _format_timestamp(seconds: float) -> str:
    """`hh:mm:ss.t` (one tenth of a second), used by plain text output."""
    if seconds < 0:
        seconds = 0.0
    total_ms = int(round(seconds * 1000))
    h, rem_ms = divmod(total_ms, 3_600_000)
    m, rem_ms = divmod(rem_ms, 60_000)
    s, ms = divmod(rem_ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms // 100}"


def _format_timestamp_seconds(seconds: float) -> str:
    """`hh:mm:ss` (no fractional part), used by Markdown output."""
    if seconds < 0:
        seconds = 0.0
    total_seconds = int(round(seconds))
    h, rem = divmod(total_seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _format_srt_timestamp(seconds: float) -> str:
    """`hh:mm:ss,mmm` — SubRip uses a comma as the decimal separator."""
    h, m, s, ms = _hms_ms(seconds)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _format_vtt_timestamp(seconds: float) -> str:
    """`hh:mm:ss.mmm` — WebVTT uses a period as the decimal separator."""
    h, m, s, ms = _hms_ms(seconds)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def _hms_ms(seconds: float) -> tuple[int, int, int, int]:
    if seconds < 0:
        seconds = 0.0
    total_ms = int(round(seconds * 1000))
    h, rem_ms = divmod(total_ms, 3_600_000)
    m, rem_ms = divmod(rem_ms, 60_000)
    s, ms = divmod(rem_ms, 1000)
    return h, m, s, ms


def _pick_text(text: dict[str, str], preferred: str | None) -> str:
    if preferred and preferred in text:
        return text[preferred]
    # Fall back to whichever language is available (deterministic order).
    for key in sorted(text.keys()):
        return text[key]
    return ""


def _sanitize_srt_text(text: str) -> str:
    """Strip content that would break SRT parsing.

    SRT separates cues with blank lines and uses ``-->`` to delimit
    timestamps. Any literal ``-->`` inside a cue body would confuse a parser,
    and trailing blank lines inside a cue would terminate it early.
    """
    cleaned = text.replace("-->", "→")
    # Collapse runs of blank lines to a single newline so the cue stays intact.
    return "\n".join(line.strip() for line in cleaned.splitlines() if line.strip())


def _escape_vtt_text(text: str) -> str:
    """Escape characters that have meaning in WebVTT cue payloads.

    WebVTT cue text is essentially a tiny subset of HTML: ``<``, ``>``, and
    ``&`` are reserved. ``-->`` would also confuse the cue-timing parser if
    it appeared at the start of a line.
    """
    # Replace the cue-timing arrow first; otherwise the '>' would become '&gt;'
    # and the literal sequence "--&gt;" would still render as "-->" in players.
    out = text.replace("-->", "→").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return "\n".join(line.strip() for line in out.splitlines() if line.strip())
