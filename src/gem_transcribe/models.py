"""Pydantic data models for transcription output."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class Segment(BaseModel):
    """A single transcribed segment.

    ``text`` maps a language code (ISO 639-1, e.g. ``"en"``, ``"ja"``) to the
    text in that language. With ``--lang=en,ja`` each segment carries both
    keys: the original-language text plus a translation.
    """

    start: float = Field(ge=0.0, description="Segment start in seconds")
    end: float = Field(ge=0.0, description="Segment end in seconds")
    speaker: str = Field(min_length=1, description="Speaker label or attributed name")
    text: dict[str, str] = Field(min_length=1, description="Language code → text")

    @field_validator("end")
    @classmethod
    def _end_after_start(cls, v: float, info) -> float:
        start = info.data.get("start")
        if start is not None and v < start:
            raise ValueError(f"end ({v}) must be >= start ({start})")
        return v

    @field_validator("text")
    @classmethod
    def _text_values_nonempty(cls, v: dict[str, str]) -> dict[str, str]:
        for lang, t in v.items():
            if not isinstance(t, str) or not t.strip():
                raise ValueError(f"text value for language {lang!r} must be a non-empty string")
        return v


class Metadata(BaseModel):
    """Metadata describing the transcription run."""

    source: str = Field(description="Original input (local path or gs:// URI)")
    model: str = Field(description="Gemini model name used")
    duration_seconds: float | None = Field(default=None, description="Audio duration if known")
    languages: list[str] = Field(min_length=1, description="Output languages requested")
    speaker_hints: list[str] = Field(default_factory=list, description="Speaker name hints supplied by the user")


class TranscriptionResult(BaseModel):
    """Complete transcription output."""

    metadata: Metadata
    segments: list[Segment] = Field(description="Ordered list of transcribed segments")
