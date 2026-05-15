# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - Unreleased

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
- `--output-dir` mode produces both `.json` and `.txt` for the same basename
- Configuration via `~/.config/gem-transcribe/config.toml`, `GEM_TRANSCRIBE_*` env vars, or CLI flags
- Application Default Credentials (ADC) for Vertex AI and GCS
- nlk-py integration: `jsonfix` for response repair, `backoff` for rate-limit retries
