# gem-transcribe

Audio transcription CLI built on Vertex AI Gemini — speaker inference, multi-language output, structured JSON.

- **Language**: Python 3.11+ / uv
- **LLM**: Vertex AI Gemini (google-genai SDK, ADC auth)
- **Series**: util-series
- **CLI**: `gem-transcribe <audio-file | gs://bucket/path> [--lang=en,ja] [--speaker-hint="A,B"] [--format json|text|md|srt|vtt] [--output-file FILE | --output-dir DIR] [--quiet] [--verbose]`
- **Input**: Local audio files (mp3/wav/m4a/flac/ogg/webm) or pre-uploaded `gs://` URIs
- **Output**: JSON (default → stdout), plain text, Markdown timeline, SubRip (SRT), or WebVTT. `--output-dir` emits both `.json` and `.txt`. SRT/VTT with multi-language `--output-file` derives `<basename>.<lang>.<ext>` per language
- **Build**: `uv build --out-dir dist/` via `make build`
- **Test**: `uv run pytest tests/ -v` via `make test`
- **Module path**: `src/gem_transcribe/`
- **Config**: `~/.config/gem-transcribe/config.toml` (sections: `[gcp]`, `[model]`, `[storage]`, `[transcribe]`); env prefix `GEM_TRANSCRIBE_`
- **Docs**: `docs/en/` (English), `docs/ja/` (Japanese) — RFP + future architecture/reference
- **Gotchas**:
    - GCS staging bucket must be pre-created and IAM-granted (Storage Object Admin)
    - Vertex AI does not support `files.upload()` — audio must be referenced via `Part.from_uri(gs://...)`
    - Audio over ~9.5 hours per request is not supported (Phase 1 returns explicit error; Phase 2 will add chunking)
    - Segment timestamps come from Gemini's audio-token estimate and drift on long audio; can also overshoot the actual audio duration (observed: 25-min audio → 30+min timestamps). Both `gemini-2.5-flash` and `gemini-2.5-pro` exhibit this. See README "Known limitations"
    - Long-running calls (multi-minute Vertex AI requests) emit one-line milestone messages on stderr by default; suppress with `--quiet`
- **Companion**: pipes into `meeting-note` for minutes structuring (responsibility separation)
