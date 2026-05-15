# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-05-15

### Added

- Single-file audio transcription via Vertex AI Gemini
- Speaker inference: by default the model attempts to extract speaker names from
  audio context (self-introductions, direct address, third-party mentions) and
  falls back to `Speaker A/B/C` labels for unidentified speakers. Optional
  `--speaker-hint` provides a closed list of candidate names
- Multi-language output via `--lang=en,ja` (original + translation in one call)
- Auto-upload local audio to GCS staging bucket; deleted after processing (override with `--keep-staging`)
- Direct `gs://` URI input (skips upload and cleanup)
- JSON (default, stdout) and plain text output formats
- Markdown timeline format (`--format=md`) — one bold-prefixed line per segment
  with `**[hh:mm:ss] Speaker**: text`
- SubRip subtitle format (`--format=srt`) with bracketed speaker prefix and
  cue-safe text sanitization (`-->` rewrites to `→`)
- WebVTT subtitle format (`--format=vtt`) using the `<v Speaker>` voice tag
  with HTML-entity escaping for `<`, `>`, `&`
- `--format=srt|vtt` with `--output-file` and multiple `--lang` values writes
  one file per language as `<basename>.<lang>.<ext>` (matches subtitle-tool
  conventions for per-language uploads)
- `--output-dir` mode produces both `.json` and `.txt` for the same basename
- Configuration via `~/.config/gem-transcribe/config.toml`, `GEM_TRANSCRIBE_*` env vars, or CLI flags
- Application Default Credentials (ADC) for Vertex AI and GCS
- nlk-py integration: `jsonfix` for response repair, `backoff` for rate-limit retries
