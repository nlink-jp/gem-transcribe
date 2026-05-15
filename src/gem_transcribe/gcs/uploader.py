"""GCS staging upload for local audio files."""

from __future__ import annotations

import logging
import mimetypes
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from google.api_core.exceptions import NotFound
from google.cloud import storage

from gem_transcribe.config import Config

logger = logging.getLogger(__name__)

# Audio MIME types Vertex AI Gemini accepts. Used as a hint when the system
# mimetypes database does not know the extension (e.g. .m4a on minimal images).
_AUDIO_MIME_HINTS = {
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".flac": "audio/flac",
    ".ogg": "audio/ogg",
    ".opus": "audio/opus",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac",
    ".webm": "audio/webm",
}


def guess_audio_mime(path: str) -> str:
    """Best-effort MIME type for an audio file path or URI."""
    suffix = Path(path).suffix.lower()
    if suffix in _AUDIO_MIME_HINTS:
        return _AUDIO_MIME_HINTS[suffix]
    guessed, _ = mimetypes.guess_type(path)
    return guessed or "application/octet-stream"


def _split_bucket_uri(bucket_uri: str) -> tuple[str, str]:
    """Split ``gs://bucket/prefix/`` into ``(bucket, prefix)``.

    The returned prefix never starts with ``/`` and always ends with ``/`` if
    non-empty.
    """
    if not bucket_uri.startswith("gs://"):
        raise ValueError(f"expected gs:// URI, got {bucket_uri!r}")
    rest = bucket_uri.removeprefix("gs://")
    bucket, _, prefix = rest.partition("/")
    if not bucket:
        raise ValueError(f"missing bucket name in {bucket_uri!r}")
    if prefix and not prefix.endswith("/"):
        prefix = prefix + "/"
    return bucket, prefix


def _split_gs_uri(gs_uri: str) -> tuple[str, str]:
    """Split ``gs://bucket/path/to/object`` into ``(bucket, blob_name)``."""
    if not gs_uri.startswith("gs://"):
        raise ValueError(f"expected gs:// URI, got {gs_uri!r}")
    rest = gs_uri.removeprefix("gs://")
    bucket, _, blob_name = rest.partition("/")
    if not bucket or not blob_name:
        raise ValueError(f"malformed gs:// URI: {gs_uri!r}")
    return bucket, blob_name


def is_gcs_uri(value: str) -> bool:
    return value.startswith("gs://")


class StagingUploader:
    """Uploads local audio to a configured staging bucket and cleans up.

    For inputs that are already ``gs://`` URIs, ``staged()`` is a no-op:
    the URI passes through unchanged and no cleanup is performed.
    """

    def __init__(self, config: Config, *, client: storage.Client | None = None) -> None:
        self._config = config
        self._client = client or storage.Client(project=config.project)
        self._bucket_name, self._prefix = _split_bucket_uri(config.staging_bucket)

    def upload_local(self, local_path: Path) -> str:
        """Upload a local file to the staging bucket. Returns the gs:// URI."""
        if not local_path.is_file():
            raise FileNotFoundError(f"audio file not found: {local_path}")
        blob_name = f"{self._prefix}{uuid.uuid4().hex}-{local_path.name}"
        mime = guess_audio_mime(str(local_path))
        bucket = self._client.bucket(self._bucket_name)
        blob = bucket.blob(blob_name)
        blob.upload_from_filename(str(local_path), content_type=mime)
        size_mb = local_path.stat().st_size / (1024 * 1024)
        gs_uri = f"gs://{self._bucket_name}/{blob_name}"
        logger.info("Uploaded %s → %s (%.1f MB, %s)", local_path, gs_uri, size_mb, mime)
        return gs_uri

    def cleanup(self, gs_uri: str) -> None:
        """Delete the staged blob. Honours ``keep_staging`` config."""
        if self._config.keep_staging:
            logger.info("keep_staging=true; leaving %s in place", gs_uri)
            return
        bucket_name, blob_name = _split_gs_uri(gs_uri)
        try:
            self._client.bucket(bucket_name).blob(blob_name).delete()
            logger.info("Deleted staging object %s", gs_uri)
        except NotFound:
            logger.warning("Staging object already gone: %s", gs_uri)
        except Exception as exc:  # noqa: BLE001 — cleanup is best-effort
            logger.warning("Failed to delete staging object %s: %s", gs_uri, exc)

    @contextmanager
    def staged(self, input_arg: str) -> Iterator[str]:
        """Yield a ``gs://`` URI for the input.

        - If ``input_arg`` is already a ``gs://`` URI it passes through and
          cleanup is skipped (the user owns the lifecycle).
        - Otherwise the local file is uploaded and removed on exit
          (unless ``keep_staging`` is set).
        """
        if is_gcs_uri(input_arg):
            yield input_arg
            return
        gs_uri = self.upload_local(Path(input_arg))
        try:
            yield gs_uri
        finally:
            self.cleanup(gs_uri)
