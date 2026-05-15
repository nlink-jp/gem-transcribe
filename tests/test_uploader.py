"""Tests for gem_transcribe.gcs.uploader."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from google.api_core.exceptions import NotFound

from gem_transcribe.config import Config
from gem_transcribe.gcs.uploader import (
    StagingUploader,
    _split_bucket_uri,
    _split_gs_uri,
    guess_audio_mime,
    is_gcs_uri,
)


class TestHelpers:
    def test_split_bucket_uri_with_prefix(self) -> None:
        assert _split_bucket_uri("gs://b/prefix/") == ("b", "prefix/")

    def test_split_bucket_uri_normalises_trailing_slash(self) -> None:
        assert _split_bucket_uri("gs://b/prefix") == ("b", "prefix/")

    def test_split_bucket_uri_no_prefix(self) -> None:
        assert _split_bucket_uri("gs://b") == ("b", "")

    def test_split_bucket_uri_rejects_non_gs(self) -> None:
        with pytest.raises(ValueError):
            _split_bucket_uri("s3://b/")

    def test_split_gs_uri(self) -> None:
        assert _split_gs_uri("gs://b/path/to/x.mp3") == ("b", "path/to/x.mp3")

    def test_split_gs_uri_rejects_bare_bucket(self) -> None:
        with pytest.raises(ValueError):
            _split_gs_uri("gs://b/")

    def test_is_gcs_uri(self) -> None:
        assert is_gcs_uri("gs://b/x")
        assert not is_gcs_uri("/local/path.mp3")
        assert not is_gcs_uri("file.mp3")

    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("foo.mp3", "audio/mpeg"),
            ("foo.wav", "audio/wav"),
            ("foo.m4a", "audio/mp4"),
            ("foo.flac", "audio/flac"),
            ("foo.unknown", "application/octet-stream"),
        ],
    )
    def test_guess_audio_mime(self, name: str, expected: str) -> None:
        assert guess_audio_mime(name) == expected


@pytest.fixture
def mock_client() -> MagicMock:
    return MagicMock()


@pytest.fixture
def uploader(sample_config: Config, mock_client: MagicMock) -> StagingUploader:
    return StagingUploader(sample_config, client=mock_client)


class TestStagingUploader:
    def test_upload_local_uses_uuid_blob_name(
        self, uploader: StagingUploader, mock_client: MagicMock, tmp_path: Path
    ) -> None:
        audio = tmp_path / "meeting.mp3"
        audio.write_bytes(b"fake audio bytes")

        bucket = MagicMock()
        blob = MagicMock()
        mock_client.bucket.return_value = bucket
        bucket.blob.return_value = blob

        uri = uploader.upload_local(audio)

        assert uri.startswith("gs://test-bucket/gem-transcribe/")
        assert uri.endswith("-meeting.mp3")
        bucket.blob.assert_called_once()
        blob_name = bucket.blob.call_args.args[0]
        # Should be: gem-transcribe/<uuid hex>-meeting.mp3
        assert blob_name.startswith("gem-transcribe/")
        assert blob_name.endswith("-meeting.mp3")
        blob.upload_from_filename.assert_called_once_with(str(audio), content_type="audio/mpeg")

    def test_upload_local_missing_file_raises(self, uploader: StagingUploader, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            uploader.upload_local(tmp_path / "missing.mp3")

    def test_cleanup_deletes_blob(self, uploader: StagingUploader, mock_client: MagicMock) -> None:
        bucket = MagicMock()
        blob = MagicMock()
        mock_client.bucket.return_value = bucket
        bucket.blob.return_value = blob

        uploader.cleanup("gs://test-bucket/gem-transcribe/abc-meeting.mp3")

        mock_client.bucket.assert_called_with("test-bucket")
        bucket.blob.assert_called_with("gem-transcribe/abc-meeting.mp3")
        blob.delete.assert_called_once()

    def test_cleanup_skipped_when_keep_staging(self, sample_config: Config, mock_client: MagicMock) -> None:
        cfg = sample_config.model_copy(update={"keep_staging": True})
        u = StagingUploader(cfg, client=mock_client)
        u.cleanup("gs://test-bucket/x")
        mock_client.bucket.assert_not_called()

    def test_cleanup_handles_not_found(self, uploader: StagingUploader, mock_client: MagicMock) -> None:
        bucket = MagicMock()
        blob = MagicMock()
        mock_client.bucket.return_value = bucket
        bucket.blob.return_value = blob
        blob.delete.side_effect = NotFound("gone")
        # Should not raise
        uploader.cleanup("gs://test-bucket/x")

    def test_staged_passes_through_gs_uri(self, uploader: StagingUploader, mock_client: MagicMock) -> None:
        with uploader.staged("gs://other-bucket/foo.mp3") as uri:
            assert uri == "gs://other-bucket/foo.mp3"
        # No upload, no cleanup
        mock_client.bucket.assert_not_called()

    def test_staged_uploads_and_cleans_local(
        self, uploader: StagingUploader, mock_client: MagicMock, tmp_path: Path
    ) -> None:
        audio = tmp_path / "x.mp3"
        audio.write_bytes(b"data")

        bucket = MagicMock()
        blob = MagicMock()
        mock_client.bucket.return_value = bucket
        bucket.blob.return_value = blob

        with uploader.staged(str(audio)) as uri:
            assert uri.startswith("gs://test-bucket/")

        # upload + delete both happened
        blob.upload_from_filename.assert_called_once()
        blob.delete.assert_called_once()

    def test_staged_cleans_up_on_exception(
        self, uploader: StagingUploader, mock_client: MagicMock, tmp_path: Path
    ) -> None:
        audio = tmp_path / "x.mp3"
        audio.write_bytes(b"data")

        bucket = MagicMock()
        blob = MagicMock()
        mock_client.bucket.return_value = bucket
        bucket.blob.return_value = blob

        with pytest.raises(RuntimeError):
            with uploader.staged(str(audio)):
                raise RuntimeError("boom")
        blob.delete.assert_called_once()
