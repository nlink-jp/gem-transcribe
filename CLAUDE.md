# CLAUDE.md — gem-transcribe

## Purpose

Audio transcription foundation CLI. Takes a single audio file (local or GCS),
sends it to Vertex AI Gemini, and returns a structured transcript with
speaker inference and optional multi-language output. Minutes generation,
summarization, and action-item extraction are handled by `meeting-note`
downstream — this tool stays narrowly focused on transcription.

## Architecture

```
src/gem_transcribe/
  __init__.py          - Version
  cli.py               - Click CLI entry point
  config.py            - Pydantic settings (TOML + env vars + CLI overrides)
  models.py            - Pydantic data models (TranscriptionResult, Segment, Metadata)
  orchestrator.py      - End-to-end transcription flow
  gcs/
    uploader.py        - Staging upload / cleanup with context manager
  llm/
    client.py          - Gemini wrapper (Part.from_uri, retry, jsonfix)
    prompts.py         - Prompt builder (speaker hints + language modes)
  output/
    formatters.py      - JSON / plain text / Markdown / SRT / VTT formatters
```

## Security Rules

1. **No external transmission**: only the configured Vertex AI Gemini endpoint
   and Google Cloud Storage staging bucket may receive data.
2. **Staging cleanup**: locally-uploaded audio MUST be deleted from GCS in a
   `finally` block (suppressed by `--keep-staging` for debugging only).
3. **Prompt injection defense**: speaker hints and other user-supplied
   metadata are wrapped via `nlk.guard.Tag` before insertion into prompts.
4. **No secret logging**: never log credentials, tokens, or the contents of
   the GCS bucket beyond opaque URIs.

## Development Rules

- Tests live alongside features in `tests/`
- Type hints required for all function signatures
- `make test` and `make lint` must pass before commit
- Small, typed commits (`feat:`, `fix:`, `test:`, `chore:`, `docs:`, `refactor:`, `security:`)
- README.md / README.ja.md updated in the same commit as user-visible changes

## LLM Configuration

Configure via `~/.config/gem-transcribe/config.toml`, environment variables
(`GEM_TRANSCRIBE_*` prefix), or CLI flags. Priority: CLI > env > .env >
config.toml > defaults.

```toml
[gcp]
project = "your-gcp-project"
location = "us-central1"

[model]
name = "gemini-2.5-flash"
max_output_tokens = 65536

[storage]
staging_bucket = "gs://your-bucket/gem-transcribe/"
keep_staging = false

[transcribe]
default_languages = ["en"]
request_timeout = 1800
```

Authentication: Application Default Credentials (ADC).
`gcloud auth application-default login`

## Communication Language

All communication between contributors and Claude Code is conducted in **Japanese**.
