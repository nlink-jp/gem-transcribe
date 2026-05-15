# RFP: gem-transcribe

> Generated: 2026-05-15
> Status: Draft

## 1. Problem Statement

A "transcription foundation" CLI built on Vertex AI Gemini. The tool serves
meeting recorders, interviewers / journalists, subtitle and translation
workflow operators, and video-content organizers who need transcripts that
include speaker inference, structured output, and multi-language support.
It sits upstream of `meeting-note` (the minutes-structuring tool) — minutes
generation, summarization, and action-item extraction are explicitly out of
scope.

The focus is narrowly on **a transcription foundation** designed as a
single-purpose CLI that composes well with other tools via UNIX pipes.

## 2. Functional Specification

### Commands / API Surface

```
gem-transcribe <audio-file | gs://bucket/path> [flags]
```

Primary flags:

| Flag | Description |
|---|---|
| `--lang=en,ja` | Output languages. Multiple values emit original + translation simultaneously |
| `--speaker-hint="Yamada,Sato"` | Speaker hints. Passed to the prompt so Gemini can attempt name attribution |
| `--format=json\|md\|srt\|vtt\|text` | Output format. Default: json |
| `--output-dir=<dir>` | Emit multiple formats at once |
| `--output-file=<path>` | Single-file output |
| `--model=flash\|pro` | Model selection. Default from config.toml |
| `--keep-staging` | Do not delete the staged audio in GCS (debug) |
| `--config=<path>` | Override config.toml path |

### Input / Output

**Input:**
- Local audio file (mp3, wav, m4a, flac, ogg, etc. — any Gemini-supported
  format). Tool auto-uploads to `staging_bucket` and deletes after processing
  by default.
- `gs://bucket/path/audio.mp3` (pre-uploaded GCS URI). Upload is skipped, no
  cleanup performed.

**Output:**
- Default: JSON to stdout
- With `--output-dir`: emits `<input-basename>.{json,md,srt,vtt,txt}` together
- With `--output-file`: single file in the format selected by `--format`

**JSON schema (draft):**

```json
{
  "metadata": {
    "source": "meeting-2026-05-15.mp3",
    "model": "gemini-2.5-flash",
    "duration_seconds": 1825.4,
    "languages": ["en", "ja"],
    "speaker_hints": ["Yamada", "Sato"]
  },
  "segments": [
    {
      "start": 0.0,
      "end": 4.2,
      "speaker": "Yamada",
      "text": {
        "en": "Let's review the quarterly results.",
        "ja": "四半期業績を見ていきましょう。"
      }
    }
  ]
}
```

### Configuration

`config.toml` (follows the unified pattern of the existing 11 Vertex AI tools):

```toml
[vertex_ai]
project_id = "your-gcp-project"
location = "us-central1"
model = "gemini-2.5-flash"

[storage]
staging_bucket = "gs://your-bucket/gem-transcribe/"

[transcribe]
default_languages = ["en"]
keep_staging = false
```

Environment variable overrides follow the nlk-py convention
(`GEM_TRANSCRIBE_*` prefix).

### External Dependencies

- **Vertex AI Gemini API** (required)
- **Google Cloud Storage** (required, for staging)
- **Python 3.11+**
- **google-genai SDK** (Vertex AI mode)
- **nlk-py** (guard / jsonfix / backoff / validate)
- **ffmpeg** (Phase 2 chunking only; not needed for Phase 1)

## 3. Design Decisions

### Why Python

If long-audio chunking becomes necessary, Python's audio ecosystem
(`pydub`, `ffmpeg-python`, `pydub.silence` for silence-aware splitting) is
significantly easier to leverage. Go would require shelling out to ffmpeg
and parsing its output by hand — a clear ergonomic gap in this domain.

In addition, sharing the language with `meeting-note` (Python / Vertex AI)
allows reuse of JSON schemas and prompt building blocks. The `nlk-py`
integration pattern is already proven in meeting-note / mail-triage /
ai-ir2 / gem-rag.

### Why complement existing tools

- **meeting-note**: minutes structuring and summarization stay there;
  gem-transcribe pipes its output into meeting-note. Schema compatibility
  is not strictly enforced — a transformation stage can sit between the
  two if needed.
- **gem-* family**: aligns naming and config.toml patterns with the
  Gemini CLI siblings in util-series (gem-search / gem-image / gem-query /
  gem-rag).

### Out of scope (explicitly excluded)

- Real-time streaming transcription (microphone input adds control
  complexity and broadens scope)
- Minutes / summary / action-item extraction (meeting-note's responsibility)
- Audio pre-processing (noise reduction, volume normalization, format
  conversion) — pass raw files to Vertex AI and lean on Gemini's robustness
- Web UI / GUI (CLI-first; if a GUI is needed later, design separately
  following the shell-agent / data-agent pattern)

## 4. Development Plan

### Phase 1: Core

- Single-file transcription (local + GCS)
- Speaker inference (A/B/C labels and hint-based name assignment;
  hints are optional)
- Multi-language output (`--lang=en,ja` produces original + translation
  in one call)
- JSON + plain text output
- `config.toml` + ADC authentication
- Auto GCS upload / delete with `--keep-staging` flag
- Robust LLM response parsing via nlk-py/jsonfix
- Rate-limit resilience via nlk-py/backoff
- Explicit error for audio over 9.5 hours
- pytest coverage (focused on prompt construction, response parsing,
  GCS upload behavior; E2E with real audio handled separately)

### Phase 2: Features

- Markdown / SRT / VTT formatters (post-processing JSON, switched via
  `--format`)

### Phase 3: Release

- README.md / README.ja.md
- CHANGELOG.md
- AGENTS.md
- E2E testing with real audio (short, medium, multi-language cases)
- v0.1.0 release

Each phase can be reviewed independently. Once Phase 1 is stable, the
project graduates from `_wip/` and is added as a util-series submodule
per CONVENTIONS.md.

## 5. Required API Scopes / Permissions

- **Vertex AI User** (`roles/aiplatform.user`) — Gemini API calls
- **Storage Object Admin** (`roles/storage.objectAdmin`) — staging bucket
  read / write / delete
  - Least-privilege alternative: `objectCreator` + `objectViewer` +
    deletion permission combined
- User pre-requisites:
  - Create a GCS bucket (same region as Vertex AI recommended)
  - Run `gcloud auth application-default login` to set up ADC

## 6. Series Placement

**Series: util-series**

Rationale:
- Pipe-friendly data transformation CLI (audio → structured text)
- Aligns perfectly with the existing Gemini siblings (gem-search /
  gem-image / gem-query / gem-rag)
- Composes naturally with meeting-note and other tools
- Personal-first usage; pip / uv tool distribution is sufficient

`lab-series` would be appropriate for experimental work, but the
requirements and design direction are firm enough to start directly
in util-series.

## 7. External Platform Constraints

### Vertex AI Gemini

- **Rate limits**: QPM / TPM caps. Frequent 429s observed in batch
  workloads (`feedback_gemini_api_rate_limit`) → mitigated via
  nlk-py/backoff (exponential backoff)
- **Audio length cap**: ~9.5 hours per request. Phase 1 returns an
  explicit error above this; Phase 2 may add chunking (pydub.silence +
  ffmpeg)
- **Files API unavailable**: Vertex AI does not support `files.upload()`
  (`feedback_vertex_files_upload`) → must use `Part.from_uri(gs://...)`
- **Gemini 3 migration**: GA expected after 2026-10-16. Migrate together
  with the existing 13 tools (`project_gemini3_migration` memory will be
  updated to include this tool). Migration also requires thought signature
  echo-back handling (`feedback_gemini3_thought_signature`)

### GCS

- The user must create the bucket and grant IAM in advance. The tool does
  not create buckets (instructions documented in README)

### Local dependencies

- ffmpeg required only when Phase 2 chunking is enabled. Not needed for
  Phase 1

### Model selection

- Default: `gemini-2.5-flash` (cost-conscious; speaker inference is at a
  practical level)
- Switchable to `gemini-2.5-pro` via `config.toml` (complex speaker
  separation, multi-language edge cases)

---

## Discussion Log

### 2026-05-15 — Initial RFP

**Tool name selection:**
- Candidates: gem-voice / gem-transcribe / gem-stt / gem-scribe
- → `gem-transcribe` (clear purpose, consistent with the gem-* family)

**Narrowing the problem statement:**
- A "multi-purpose all-in-one" framing was considered but rejected due
  to scope-creep risk
- → **Focus on "transcription foundation"** to clearly separate
  responsibilities from meeting-note

**Speaker inference level:**
- Labels-only / hint-based names / both
- → **Both, with optional hints**. Branching handled in prompt design

**Input mechanism debate:**
- Initial proposal included inline base64 with auto GCS fallback
- User feedback redirected to **GCS bucket as the primary path** (inline
  base64 is impractical for long audio)
- Local files auto-upload to the staging bucket; deleted after processing
  by default

**Implementation language:**
- Go (visual consistency with gem-* family) vs Python (audio ecosystem
  advantage)
- For long-audio chunking, Python is clearly easier (pydub /
  pydub.silence)
- JSON schema reuse with meeting-note, proven nlk-py integration pattern
- → **Python selected**. Picking Go for naming aesthetics in an
  audio-domain tool would be putting form over substance

**Out-of-scope items confirmed:**
- Real-time streaming, minutes/summary/action items, audio pre-processing,
  Web UI / GUI

**Phase 1 / Phase 2 split:**
- Phase 1: single-file transcription + speaker inference + multi-language
  + JSON
- Phase 2: Markdown / SRT / VTT formatters
- Auto chunking, batch mode, speaker profile persistence — deferred

**Series placement:**
- util-series (pipe-friendly, aligns with the gem-* family)
- No need to incubate in lab-series — requirements and design are firm

**Recorded constraints:**
- Vertex AI rate limits, GCS pre-setup, 9.5-hour cap, ffmpeg local
  dependency (Phase 2)
- Gemini 3 migration handled together with other tools (recorded only)
