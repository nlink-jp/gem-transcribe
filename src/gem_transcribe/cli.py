"""Click CLI for gem-transcribe."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import click

from gem_transcribe import __version__
from gem_transcribe.config import get_config
from gem_transcribe.gcs.uploader import is_gcs_uri
from gem_transcribe.models import TranscriptionResult
from gem_transcribe.orchestrator import transcribe
from gem_transcribe.output.formatters import to_json, to_markdown, to_srt, to_text, to_vtt

# Format → (renderer, file extension) mapping. Keep aligned with the
# --format Click choice list below.
_FORMATTERS = {
    "json": (to_json, "json"),
    "text": (to_text, "txt"),
    "md": (to_markdown, "md"),
    "srt": (to_srt, "srt"),
    "vtt": (to_vtt, "vtt"),
}
_PER_LANGUAGE_FORMATS = frozenset({"srt", "vtt"})


def _parse_csv(value: str | None) -> list[str] | None:
    if not value:
        return None
    parts = [p.strip() for p in value.split(",")]
    return [p for p in parts if p] or None


def _resolve_basename(input_arg: str) -> str:
    if is_gcs_uri(input_arg):
        return Path(input_arg.removeprefix("gs://").split("/", 1)[-1]).stem or "transcript"
    return Path(input_arg).stem or "transcript"


def _per_language_paths(output_file: Path, languages: list[str], extension: str) -> list[tuple[str, Path]]:
    """Derive ``<basename>.<lang>.<ext>`` paths for each language.

    The supplied ``output_file`` may or may not already carry the format
    extension; it is normalised to ``.<ext>`` before the language code is
    spliced in. Languages are deduplicated while preserving order.
    """
    seen: set[str] = set()
    unique = [lang for lang in languages if not (lang in seen or seen.add(lang))]
    canonical = output_file.with_suffix(f".{extension}")
    stem = canonical.stem
    parent = canonical.parent
    return [(lang, parent / f"{stem}.{lang}.{extension}") for lang in unique]


def _write_outputs(
    result: TranscriptionResult,
    *,
    fmt: str,
    output_file: str | None,
    output_dir: str | None,
    input_arg: str,
    languages: list[str],
) -> None:
    if output_dir:
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        base = _resolve_basename(input_arg)
        json_path = out_dir / f"{base}.json"
        text_path = out_dir / f"{base}.txt"
        json_path.write_text(to_json(result), encoding="utf-8")
        text_path.write_text(to_text(result), encoding="utf-8")
        click.echo(f"Wrote {json_path}", err=True)
        click.echo(f"Wrote {text_path}", err=True)
        return

    renderer, extension = _FORMATTERS[fmt]

    # Multi-language SRT/VTT with --output-file: derive per-language paths so
    # each subtitle file holds exactly one language (matches subtitle-tool
    # conventions and YouTube uploads).
    if output_file and fmt in _PER_LANGUAGE_FORMATS and len(languages) > 1:
        for lang, path in _per_language_paths(Path(output_file), languages, extension):
            path.write_text(renderer(result, language=lang), encoding="utf-8")
            click.echo(f"Wrote {path}", err=True)
        return

    rendered = renderer(result)
    if output_file:
        Path(output_file).write_text(rendered, encoding="utf-8")
        click.echo(f"Wrote {output_file}", err=True)
    else:
        click.echo(rendered)


@click.command()
@click.argument("input_arg", metavar="AUDIO")
@click.option("--lang", "lang_csv", default=None, help="Output languages, comma-separated (e.g. en,ja)")
@click.option(
    "--speaker-hint",
    "speaker_hint_csv",
    default=None,
    help="Comma-separated participant names for speaker attribution",
)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["json", "text", "md", "srt", "vtt"], case_sensitive=False),
    default="json",
    show_default=True,
    help=(
        "Output format (ignored when --output-dir is set). srt/vtt with "
        "--output-file and multiple --lang values produces one file per "
        "language as <basename>.<lang>.<ext>."
    ),
)
@click.option("--output-file", default=None, type=click.Path(dir_okay=False), help="Write output to a single file")
@click.option(
    "--output-dir",
    default=None,
    type=click.Path(file_okay=False),
    help="Write both .json and .txt for the input basename into this directory",
)
@click.option("--model", default=None, help="Override the configured Gemini model")
@click.option("--project", default=None, help="Override GCP project")
@click.option("--location", default=None, help="Override GCP location")
@click.option("--staging-bucket", default=None, help="Override staging bucket (gs://...)")
@click.option(
    "--keep-staging/--no-keep-staging",
    default=None,
    help="Keep uploaded staging objects (debug only). Defaults to config.",
)
@click.option(
    "--config",
    "config_path",
    default=None,
    type=click.Path(dir_okay=False),
    help="Path to config.toml (default: ~/.config/gem-transcribe/config.toml)",
)
@click.option("-v", "--verbose", is_flag=True, default=False, help="Enable INFO-level logging on stderr")
@click.option(
    "-q",
    "--quiet",
    is_flag=True,
    default=False,
    help="Suppress progress messages on stderr (default: show milestone updates)",
)
@click.version_option(__version__, prog_name="gem-transcribe")
def main(
    input_arg: str,
    lang_csv: str | None,
    speaker_hint_csv: str | None,
    fmt: str,
    output_file: str | None,
    output_dir: str | None,
    model: str | None,
    project: str | None,
    location: str | None,
    staging_bucket: str | None,
    keep_staging: bool | None,
    config_path: str | None,
    verbose: bool,
    quiet: bool,
) -> None:
    """Transcribe AUDIO (a local path or a gs:// URI) using Vertex AI Gemini."""
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if output_file and output_dir:
        raise click.UsageError("--output-file and --output-dir are mutually exclusive")

    overrides: dict = {}
    if project:
        overrides["project"] = project
    if location:
        overrides["location"] = location
    if model:
        overrides["model"] = model
    if staging_bucket:
        overrides["staging_bucket"] = staging_bucket
    if keep_staging is not None:
        overrides["keep_staging"] = keep_staging

    try:
        config = get_config(
            config_path=Path(config_path) if config_path else None,
            **overrides,
        )
    except ValueError as exc:
        raise click.UsageError(str(exc)) from exc

    languages = _parse_csv(lang_csv)
    speaker_hints = _parse_csv(speaker_hint_csv)

    def reporter(msg: str) -> None:
        if not quiet:
            click.echo(msg, err=True)

    try:
        result = transcribe(
            input_arg,
            config=config,
            languages=languages,
            speaker_hints=speaker_hints,
            reporter=reporter,
        )
    except FileNotFoundError as exc:
        raise click.FileError(str(exc)) from exc

    _write_outputs(
        result,
        fmt=fmt.lower(),
        output_file=output_file,
        output_dir=output_dir,
        input_arg=input_arg,
        languages=result.metadata.languages,
    )


if __name__ == "__main__":
    main()
