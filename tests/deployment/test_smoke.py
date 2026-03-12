"""
Deployment smoke tests — quick validation that the deployment is healthy.

This suite should complete in under 60 seconds.  It covers health probes,
SAS token generation, file-type rejection, upload pipeline, status queries,
download guards, deletion, CORS headers, and error handling.

Usage::

    # Quick smoke (< 60s)
    pytest tests/deployment/test_smoke.py -v -m smoke

    # Against Azure
    BASE_URL=https://ca-pdftohtml-api.azurecontainerapps.io \
        pytest tests/deployment/test_smoke.py -v -m smoke
"""

from __future__ import annotations

import os
import uuid

import pytest
import requests

from tests.deployment.conftest import (
    BASE_URL,
    cleanup_document,
    upload_file,
    wait_for_completion,
)

# Minimal valid PDF with selectable text (reused from test_api_smoke.py)
MINIMAL_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
    b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]\n"
    b"   /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
    b"4 0 obj\n<< /Length 44 >>\nstream\n"
    b"BT /F1 24 Tf 100 700 Td (Hello WCAG) Tj ET\n"
    b"endstream\nendobj\n"
    b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
    b"xref\n0 6\n"
    b"0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n"
    b"0000000115 00000 n \n0000000266 00000 n \n0000000360 00000 n \n"
    b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n441\n%%EOF"
)

# Path for inline-uploaded minimal PDF (written once per session)
_TINY_PDF_PATH = "/tmp/_smoke_test_tiny.pdf"


@pytest.fixture(scope="session", autouse=True)
def _write_tiny_pdf():
    """Write the minimal PDF to disk so ``upload_file()`` can use it."""
    with open(_TINY_PDF_PATH, "wb") as f:
        f.write(MINIMAL_PDF)
    yield
    try:
        os.remove(_TINY_PDF_PATH)
    except OSError:
        pass


# ── helpers ────────────────────────────────────────────────────────────────


def _sas_token_request(filename: str, content_type: str, size_bytes: int = 1024):
    """POST /api/upload/sas-token and return the response object."""
    return requests.post(
        f"{BASE_URL}/api/upload/sas-token",
        json={
            "filename": filename,
            "content_type": content_type,
            "size_bytes": size_bytes,
        },
        timeout=30,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Suite 1 — Smoke Tests
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.smoke
class TestHealthAndReadiness:
    """1. Health & Readiness: /health returns 200 with storage+queue checks."""

    def test_health_returns_200(self):
        resp = requests.get(f"{BASE_URL}/health", timeout=30)
        assert resp.status_code == 200

    def test_health_has_status(self):
        data = requests.get(f"{BASE_URL}/health", timeout=30).json()
        assert data["status"] in ("healthy", "degraded")

    def test_health_checks_storage(self):
        data = requests.get(f"{BASE_URL}/health", timeout=30).json()
        assert "checks" in data
        assert data["checks"]["storage"] == "ok", (
            f"Storage check failed — blob storage unreachable: {data}"
        )

    def test_health_checks_queue(self):
        data = requests.get(f"{BASE_URL}/health", timeout=30).json()
        assert data["checks"]["queue"] == "ok", (
            f"Queue check failed — storage queue unreachable: {data}"
        )

    def test_ready_returns_200(self):
        resp = requests.get(f"{BASE_URL}/ready", timeout=30)
        assert resp.status_code == 200


@pytest.mark.smoke
class TestSasTokenGeneration:
    """2. SAS Token Generation: valid tokens for .pdf, .docx, .pptx."""

    @pytest.mark.parametrize(
        "filename, content_type",
        [
            ("report.pdf", "application/pdf"),
            (
                "report.docx",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ),
            (
                "slides.pptx",
                "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            ),
        ],
        ids=["pdf", "docx", "pptx"],
    )
    def test_valid_file_types_return_sas(self, filename, content_type):
        resp = _sas_token_request(filename, content_type)
        assert resp.status_code == 200, f"SAS failed for {filename}: {resp.text}"
        data = resp.json()
        assert "document_id" in data
        assert "upload_url" in data
        assert "expires_at" in data
        # URL should point at real blob storage
        url = data["upload_url"]
        assert "blob.core.windows.net" in url or "devstoreaccount1" in url

        # Cleanup the placeholder
        cleanup_document(data["document_id"])


@pytest.mark.smoke
class TestFileTypeRejection:
    """3. File Type Rejection: .exe, .bat, .sh are rejected with 400."""

    @pytest.mark.parametrize(
        "filename, content_type",
        [
            ("malware.exe", "application/octet-stream"),
            ("script.bat", "application/octet-stream"),
            ("setup.sh", "application/x-sh"),
        ],
        ids=["exe", "bat", "sh"],
    )
    def test_dangerous_extension_returns_400(self, filename, content_type):
        resp = _sas_token_request(filename, content_type)
        assert resp.status_code == 400, (
            f"Expected 400 for {filename}, got {resp.status_code}: {resp.text}"
        )


@pytest.mark.smoke
class TestUploadPipelineQuickCheck:
    """4. Upload Pipeline Quick Check: upload via SAS, verify in status."""

    @pytest.fixture(autouse=True)
    def _cleanup_docs(self):
        self._doc_ids: list[str] = []
        yield
        for doc_id in self._doc_ids:
            cleanup_document(doc_id)

    def test_upload_appears_in_status(self):
        doc_id = upload_file(_TINY_PDF_PATH, filename="smoke-quick.pdf")
        self._doc_ids.append(doc_id)

        # Immediately query status — should exist (pending or processing)
        resp = requests.get(
            f"{BASE_URL}/api/documents/status",
            params={"document_id": doc_id},
            timeout=30,
        )
        assert resp.status_code == 200, f"Status check failed: {resp.text}"
        data = resp.json()
        assert data.get("document_id") == doc_id
        assert data.get("status") in ("pending", "processing", "completed")


@pytest.mark.smoke
class TestStatusEndpoint:
    """5. Status Endpoint: GET /api/documents/status returns proper JSON."""

    def test_status_all_returns_documents_and_summary(self):
        resp = requests.get(f"{BASE_URL}/api/documents/status", timeout=30)
        assert resp.status_code == 200
        data = resp.json()
        assert "documents" in data, f"Missing 'documents' key: {data.keys()}"
        assert "summary" in data or "batch_summary" in data, (
            f"Missing summary key: {data.keys()}"
        )
        assert isinstance(data["documents"], list)


@pytest.mark.smoke
class TestDownloadBeforeReady:
    """6. Download Before Ready: pending doc returns 409."""

    @pytest.fixture(autouse=True)
    def _cleanup_docs(self):
        self._doc_ids: list[str] = []
        yield
        for doc_id in self._doc_ids:
            cleanup_document(doc_id)

    def test_download_pending_returns_409(self):
        # Request SAS token but do NOT upload — document stays pending
        resp = _sas_token_request("pending-smoke.pdf", "application/pdf")
        assert resp.status_code == 200
        doc_id = resp.json()["document_id"]
        self._doc_ids.append(doc_id)

        dl_resp = requests.get(
            f"{BASE_URL}/api/documents/{doc_id}/download", timeout=30,
        )
        assert dl_resp.status_code == 409, (
            f"Expected 409 for pending doc, got {dl_resp.status_code}: {dl_resp.text}"
        )


@pytest.mark.smoke
class TestDeleteEndpoint:
    """7. Delete Endpoint: DELETE works and document disappears."""

    def test_delete_removes_document(self):
        doc_id = upload_file(_TINY_PDF_PATH, filename="delete-smoke.pdf")

        # Wait for conversion so it's safe to delete
        wait_for_completion(doc_id, timeout=60)

        # Delete
        del_resp = requests.delete(
            f"{BASE_URL}/api/documents/{doc_id}", timeout=30,
        )
        assert del_resp.status_code == 200

        # Verify it's gone
        status_resp = requests.get(
            f"{BASE_URL}/api/documents/status",
            params={"document_id": doc_id},
            timeout=30,
        )
        assert status_resp.status_code == 404


@pytest.mark.smoke
class TestCorsHeaders:
    """8. CORS Headers: verify CORS headers are present on API responses."""

    def test_cors_headers_on_options_preflight(self):
        resp = requests.options(
            f"{BASE_URL}/api/upload/sas-token",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type",
            },
            timeout=30,
        )
        # FastAPI CORS middleware responds to OPTIONS with 200
        assert resp.status_code == 200, (
            f"CORS preflight failed ({resp.status_code}): {resp.text}"
        )
        assert "access-control-allow-origin" in resp.headers, (
            f"Missing CORS header. Headers: {dict(resp.headers)}"
        )

    def test_cors_headers_on_get_health(self):
        resp = requests.get(
            f"{BASE_URL}/health",
            headers={"Origin": "http://localhost:3000"},
            timeout=30,
        )
        assert resp.status_code == 200
        # The allow-origin header should be present when Origin is sent
        assert "access-control-allow-origin" in resp.headers, (
            f"No CORS header on /health. Headers: {dict(resp.headers)}"
        )


@pytest.mark.smoke
class TestErrorHandling:
    """9. Error Handling: invalid IDs return 404, not 500."""

    def test_invalid_document_id_returns_404(self):
        fake_id = str(uuid.uuid4())
        resp = requests.get(
            f"{BASE_URL}/api/documents/status",
            params={"document_id": fake_id},
            timeout=30,
        )
        assert resp.status_code == 404, (
            f"Expected 404 for unknown doc, got {resp.status_code}: {resp.text}"
        )

    def test_download_nonexistent_returns_404(self):
        fake_id = str(uuid.uuid4())
        resp = requests.get(
            f"{BASE_URL}/api/documents/{fake_id}/download",
            timeout=30,
        )
        assert resp.status_code in (404, 409), (
            f"Expected 404/409, got {resp.status_code}: {resp.text}"
        )

    def test_delete_nonexistent_returns_404(self):
        fake_id = str(uuid.uuid4())
        resp = requests.delete(
            f"{BASE_URL}/api/documents/{fake_id}", timeout=30,
        )
        assert resp.status_code == 404, (
            f"Expected 404, got {resp.status_code}: {resp.text}"
        )

    def test_sas_token_missing_filename_returns_error(self):
        resp = requests.post(
            f"{BASE_URL}/api/upload/sas-token",
            json={"content_type": "application/pdf", "size_bytes": 1024},
            timeout=30,
        )
        # Should be 400 or 422, definitely not 500
        assert resp.status_code < 500, (
            f"Server error for missing filename: {resp.status_code}: {resp.text}"
        )
