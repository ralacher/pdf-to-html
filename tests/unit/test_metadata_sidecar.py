"""Tests for the metadata sidecar mechanism.

When a browser PUTs file content via a SAS URL, Azure Blob Storage
overwrites the entire blob — including any metadata set on the
placeholder.  The *sidecar* pattern stores metadata in a separate
``.meta/{document_id}.json`` blob that survives the content overwrite.

These tests verify:
  1. The SAS-token endpoint creates the sidecar blob.
  2. The worker recovers metadata from the sidecar when the main blob's
     metadata is missing.
  3. The worker falls back to reconstruction when no sidecar exists.
  4. The recovered metadata contains the correct ``name`` field.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, call, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FILENAME = "quarterly-report.pdf"
_DOC_NAME = "quarterly-report"
_DOC_ID = "cafebabe-0000-0000-0000-000000000001"
_BLOB_NAME = f"{_DOC_ID}.pdf"

_INITIAL_METADATA: dict[str, str] = {
    "document_id": _DOC_ID,
    "name": _DOC_NAME,
    "original_filename": _FILENAME,
    "format": "pdf",
    "size_bytes": "102400",
    "upload_timestamp": "2025-01-15T10:00:00+00:00",
    "status": "pending",
    "error_message": "",
    "page_count": "",
    "pages_processed": "0",
    "has_review_flags": "False",
    "blob_path": f"input-documents/{_BLOB_NAME}",
    "output_path": "",
    "review_pages": "[]",
    "processing_time_ms": "",
    "is_compliant": "",
}


# ---------------------------------------------------------------------------
# 1. SAS endpoint creates metadata sidecar
# ---------------------------------------------------------------------------


class TestSasEndpointCreatesSidecar:
    """Verify ``POST /api/upload/sas-token`` writes ``.meta/{id}.json``."""

    @patch("app.main.is_local_storage", return_value=False)
    @patch("app.main.retry_blob_operation", side_effect=lambda fn: fn())
    @patch("app.main.generate_sas_token_str", return_value="sig=abc")
    @patch("app.main.get_blob_service_client")
    @patch("app.main.uuid.uuid4", return_value=_DOC_ID)
    def test_sas_endpoint_creates_metadata_sidecar(
        self,
        mock_uuid: MagicMock,
        mock_blob_svc: MagicMock,
        mock_sas: MagicMock,
        mock_retry: MagicMock,
        mock_local: MagicMock,
    ) -> None:
        """After creating the placeholder blob, a sidecar is written."""
        # Arrange: mock blob service / container / blob clients
        mock_container = MagicMock()
        mock_blob_svc.return_value.get_container_client.return_value = (
            mock_container
        )
        mock_blob_svc.return_value.account_name = "devstoreaccount1"

        mock_blob_client = MagicMock()
        mock_meta_client = MagicMock()

        # get_blob_client returns the blob client for the main blob first,
        # then the meta-sidecar client for the second call.
        mock_container.get_blob_client.side_effect = [
            mock_blob_client,
            mock_meta_client,
        ]

        # Act: import and call the endpoint synchronously via TestClient
        from fastapi.testclient import TestClient

        from app.main import app

        client = TestClient(app)
        resp = client.post(
            "/api/upload/sas-token",
            json={
                "filename": _FILENAME,
                "content_type": "application/pdf",
                "size_bytes": 102400,
            },
        )

        # Assert: response is 200 and the sidecar blob was written
        assert resp.status_code == 200
        body = resp.json()
        assert body["document_id"] == _DOC_ID

        # The container should have been asked for TWO blob clients:
        #   1. The main document blob  (document_id + ext)
        #   2. The sidecar blob        (.meta/document_id.json)
        blob_client_calls = mock_container.get_blob_client.call_args_list
        blob_paths = [c.args[0] for c in blob_client_calls]
        assert f"{_DOC_ID}.pdf" in blob_paths
        assert f".meta/{_DOC_ID}.json" in blob_paths

        # The sidecar blob should have been uploaded with JSON metadata
        mock_meta_client.upload_blob.assert_called_once()
        upload_args = mock_meta_client.upload_blob.call_args
        sidecar_body = json.loads(upload_args.args[0])
        assert sidecar_body["name"] == _DOC_NAME
        assert sidecar_body["original_filename"] == _FILENAME
        assert sidecar_body["document_id"] == _DOC_ID


# ---------------------------------------------------------------------------
# 2. Worker recovers metadata from sidecar
# ---------------------------------------------------------------------------


class _StopPipeline(Exception):
    """Sentinel exception used to halt the worker pipeline after metadata."""


class TestWorkerRecoversSidecar:
    """Verify ``_convert`` reads ``.meta/{id}.json`` when metadata is gone."""

    @patch("app.worker.check_password_protection", side_effect=_StopPipeline)
    @patch("app.worker.status_service")
    @patch("app.worker.get_blob_service_client")
    def test_worker_recovers_metadata_from_sidecar(
        self,
        mock_blob_svc: MagicMock,
        mock_status_svc: MagicMock,
        mock_check_pw: MagicMock,
    ) -> None:
        """When the main blob has no metadata, the sidecar is read and
        the metadata is re-applied to the main blob."""
        from app.worker import ConversionWorker

        # -- Mock the main blob client --
        mock_container = MagicMock()
        mock_blob_svc.return_value.get_container_client.return_value = (
            mock_container
        )

        mock_blob_client = MagicMock()
        mock_meta_client = MagicMock()

        # First call → main blob, second → sidecar
        mock_container.get_blob_client.side_effect = [
            mock_blob_client,
            mock_meta_client,
        ]

        # Main blob has content but NO metadata (simulates SAS overwrite)
        mock_blob_client.download_blob.return_value.readall.return_value = (
            b"%PDF-1.4 fake content"
        )
        empty_props = MagicMock()
        empty_props.metadata = {}  # metadata wiped!
        empty_props.size = 21
        mock_blob_client.get_blob_properties.return_value = empty_props

        # Sidecar blob returns the original metadata
        mock_meta_client.download_blob.return_value.readall.return_value = (
            json.dumps(_INITIAL_METADATA).encode()
        )

        worker = ConversionWorker()
        # _StopPipeline is raised inside the worker's try/except for the
        # conversion pipeline, so it is caught and logged — it won't
        # propagate.  We just need _convert to finish.
        worker._convert(_BLOB_NAME)

        # The worker should have re-applied the sidecar metadata
        mock_blob_client.set_blob_metadata.assert_called_once_with(
            metadata=_INITIAL_METADATA
        )


# ---------------------------------------------------------------------------
# 3. Worker handles missing sidecar gracefully
# ---------------------------------------------------------------------------


class TestWorkerMissingSidecar:
    """Verify fallback reconstruction when no sidecar exists."""

    @patch("app.worker.check_password_protection", side_effect=_StopPipeline)
    @patch("app.worker.status_service")
    @patch("app.worker.get_blob_service_client")
    def test_worker_handles_missing_sidecar_gracefully(
        self,
        mock_blob_svc: MagicMock,
        mock_status_svc: MagicMock,
        mock_check_pw: MagicMock,
    ) -> None:
        """No sidecar → the worker reconstructs metadata from the blob
        filename (existing fallback behaviour)."""
        from app.worker import ConversionWorker

        mock_container = MagicMock()
        mock_blob_svc.return_value.get_container_client.return_value = (
            mock_container
        )

        mock_blob_client = MagicMock()
        mock_meta_client = MagicMock()

        mock_container.get_blob_client.side_effect = [
            mock_blob_client,
            mock_meta_client,
        ]

        # Main blob: content present, metadata empty
        mock_blob_client.download_blob.return_value.readall.return_value = (
            b"%PDF-1.4 fake content"
        )
        empty_props = MagicMock()
        empty_props.metadata = {}
        empty_props.size = 21
        mock_blob_client.get_blob_properties.return_value = empty_props

        # Sidecar blob does NOT exist
        mock_meta_client.download_blob.side_effect = Exception("BlobNotFound")

        worker = ConversionWorker()
        worker._convert(_BLOB_NAME)

        # The worker should have called set_blob_metadata with
        # reconstructed metadata that uses the UUID as the name fallback.
        mock_blob_client.set_blob_metadata.assert_called_once()
        reconstructed = mock_blob_client.set_blob_metadata.call_args.args[0]
        assert reconstructed["document_id"] == _DOC_ID
        # With no sidecar and no existing metadata, name falls back to
        # the document_id (UUID).
        assert reconstructed["name"] == _DOC_ID


# ---------------------------------------------------------------------------
# 4. Recovered metadata has correct name field
# ---------------------------------------------------------------------------


class TestRecoveredMetadataName:
    """Verify the ``name`` field from the sidecar matches the original."""

    @patch("app.worker.check_password_protection", side_effect=_StopPipeline)
    @patch("app.worker.status_service")
    @patch("app.worker.get_blob_service_client")
    def test_recovered_metadata_has_correct_name(
        self,
        mock_blob_svc: MagicMock,
        mock_status_svc: MagicMock,
        mock_check_pw: MagicMock,
    ) -> None:
        """The sidecar stores ``name: 'live-ocr-demo'``; after recovery
        the blob's metadata should carry that same value — not the UUID."""
        from app.worker import ConversionWorker

        mock_container = MagicMock()
        mock_blob_svc.return_value.get_container_client.return_value = (
            mock_container
        )

        mock_blob_client = MagicMock()
        mock_meta_client = MagicMock()

        mock_container.get_blob_client.side_effect = [
            mock_blob_client,
            mock_meta_client,
        ]

        # Main blob has content but metadata wiped
        mock_blob_client.download_blob.return_value.readall.return_value = (
            b"%PDF-1.4 fake"
        )
        empty_props = MagicMock()
        empty_props.metadata = {}
        empty_props.size = 14
        mock_blob_client.get_blob_properties.return_value = empty_props

        # Sidecar has the original metadata with correct name
        sidecar_meta = dict(_INITIAL_METADATA)
        sidecar_meta["name"] = "live-ocr-demo"
        sidecar_meta["original_filename"] = "live-ocr-demo.pdf"
        mock_meta_client.download_blob.return_value.readall.return_value = (
            json.dumps(sidecar_meta).encode()
        )

        worker = ConversionWorker()
        worker._convert(_BLOB_NAME)

        # The metadata applied to the blob should have the sidecar name
        mock_blob_client.set_blob_metadata.assert_called_once_with(
            metadata=sidecar_meta
        )
        applied = mock_blob_client.set_blob_metadata.call_args[1]["metadata"]
        assert applied["name"] == "live-ocr-demo"
        assert applied["original_filename"] == "live-ocr-demo.pdf"
        assert applied["name"] != _DOC_ID  # NOT the UUID
