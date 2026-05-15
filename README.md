# gem-transcribe

Audio transcription CLI built on Vertex AI Gemini — speaker inference,
multi-language output, and structured JSON.

`gem-transcribe` is a focused "transcription foundation": one audio file in,
a structured transcript out. Minutes generation, summarization, and
action-item extraction live downstream in tools like
[meeting-note](https://github.com/nlink-jp/meeting-note).

## Features

- **Speaker inference** — by default, names are inferred from the audio
  itself (self-introductions, direct address, third-party mentions). Speakers
  whose names cannot be determined are labelled `Speaker A`, `Speaker B`, etc.
  Provide `--speaker-hint="Yamada,Sato"` to give Gemini a closed list of
  candidate names
- **Multi-language output** — `--lang=en,ja` produces both the original and a
  translation in a single API call
- **Long audio support** — local files are auto-uploaded to a GCS staging
  bucket and removed after processing; pre-uploaded `gs://` URIs are also
  accepted directly
- **Multiple output formats** — JSON to stdout by default, plus
  `--format text|md|srt|vtt`. With multi-language SRT/VTT and
  `--output-file=meeting.srt --lang=en,ja`, the tool writes
  `meeting.en.srt` and `meeting.ja.srt` automatically. `--output-dir` emits
  both `.json` and `.txt` for the same basename
- **Progress on stderr** — the CLI prints one-line milestones (upload,
  transcribe start, elapsed time on completion) so long-running calls do
  not appear frozen. Pass `--quiet` to suppress, or `--verbose` for full
  INFO-level logs

## Installation

```bash
uv tool install git+https://github.com/nlink-jp/gem-transcribe.git
# or, from a clone
uv sync --all-extras
```

Requires Python 3.11+.

## Setup

1. **Create a GCS bucket** for staging uploads:

   ```bash
   gsutil mb -l us-central1 gs://your-bucket
   ```

2. **Configure ADC** (Application Default Credentials):

   ```bash
   gcloud auth application-default login
   ```

3. **Create the config file** at `~/.config/gem-transcribe/config.toml`
   (see `config.example.toml` for the full template):

   ```toml
   [gcp]
   project = "your-gcp-project"
   location = "us-central1"

   [model]
   name = "gemini-2.5-flash"

   [storage]
   staging_bucket = "gs://your-bucket/gem-transcribe/"
   ```

   The IAM principal must hold `roles/aiplatform.user` and
   `roles/storage.objectAdmin` on the staging bucket.

## Usage

```bash
# JSON to stdout (default)
gem-transcribe meeting.mp3

# Multi-language output
gem-transcribe interview.m4a --lang=en,ja

# Speaker name attribution
gem-transcribe meeting.mp3 --speaker-hint="Yamada,Sato,Tanaka"

# Both JSON and plain text into a directory
gem-transcribe meeting.mp3 --output-dir=./transcripts/

# Markdown timeline
gem-transcribe meeting.mp3 --format=md --output-file=meeting.md

# SRT subtitles
gem-transcribe meeting.mp3 --format=srt --output-file=meeting.srt

# Multi-language SRT — writes meeting.en.srt and meeting.ja.srt
gem-transcribe meeting.mp3 --lang=en,ja --format=srt --output-file=meeting.srt

# WebVTT subtitles (with <v Speaker> voice tag)
gem-transcribe meeting.mp3 --format=vtt --output-file=meeting.vtt

# Pre-uploaded audio in GCS
gem-transcribe gs://your-bucket/recordings/2026-05-15.mp3
```

## Known limitations

### Timestamp accuracy

Segment `start` / `end` values come from Gemini's audio-token estimate, not
from sample-accurate decoding. Treat them as **rough markers, not sync-grade
references.** Concretely:

- **Drift accumulates on long audio.** Single-pass transcription of long
  recordings (roughly 20 minutes and up) drifts noticeably, with errors
  growing toward the end of the file. Short recordings (a few minutes) are
  usually within a second or two.
- **Timestamps can exceed the actual audio duration.** In real-world tests
  with `gemini-2.5-pro`, a 25-minute recording produced segments tagged past
  the 30-minute mark. Both `gemini-2.5-flash` and `gemini-2.5-pro` show this
  behaviour; switching model does **not** reliably fix it.
- **`end` is occasionally emitted as a duration** instead of an absolute
  offset (a known Gemini 2.5 quirk). The orchestrator detects and rewrites
  these cases (`end = start + end`) and logs a warning under `--verbose`.

If you need sample-accurate alignment (e.g. burning subtitles onto video),
do not consume these timestamps directly. Established workarounds — out of
scope for this tool and intended for downstream pipelines:

- Measure the audio's true duration locally (`ffprobe`) and clip / rescale
  segment timestamps against it.
- Split the audio into shorter chunks before transcription and re-offset
  each chunk's timestamps. Bounds drift to the chunk length.
- Use a dedicated forced-alignment pass (e.g. WhisperX) on the produced
  text against the original audio.

## Configuration

Priority (high → low):

1. CLI flags
2. Environment variables (`GEM_TRANSCRIBE_*`)
3. `.env` file
4. `~/.config/gem-transcribe/config.toml`
5. Built-in defaults

## Build and test

```bash
make test     # uv run pytest tests/ -v
make lint     # ruff check + format check
make build    # uv build --out-dir dist/
```

## Documentation

- [docs/en/gem-transcribe-rfp.md](docs/en/gem-transcribe-rfp.md) — design RFP
- [docs/ja/gem-transcribe-rfp.ja.md](docs/ja/gem-transcribe-rfp.ja.md) — 設計 RFP

## License

MIT
