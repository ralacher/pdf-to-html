"""
Deployment test configuration.

These tests hit a LIVE backend — they need a running API + worker.
Set BASE_URL to target Azure or local.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
import requests


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")

# Content-type mappings for supported file types
_CONTENT_TYPES: dict[str, str] = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}


# ---------------------------------------------------------------------------
# Marker registration
# ---------------------------------------------------------------------------

def pytest_configure(config):
    """Register deployment markers."""
    config.addinivalue_line("markers", "deployment: tests that hit a live backend")
    config.addinivalue_line("markers", "smoke: quick deployment health checks (< 60s)")
    config.addinivalue_line("markers", "e2e: end-to-end conversion quality evaluations (2-5 min)")


def pytest_collection_modifyitems(items):
    """Auto-mark all tests in this directory as deployment tests."""
    for item in items:
        if "deployment" in str(item.fspath):
            item.add_marker(pytest.mark.deployment)


# ---------------------------------------------------------------------------
# Session-scoped health gate
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
def verify_backend_reachable():
    """Fail fast if the backend isn't running."""
    try:
        resp = requests.get(f"{BASE_URL}/health", timeout=10)
        if resp.status_code != 200:
            pytest.skip(f"Backend at {BASE_URL} returned {resp.status_code}")
    except requests.ConnectionError:
        pytest.skip(
            f"Backend not reachable at {BASE_URL}. "
            f"Start with: uvicorn app.main:app --port 8000"
        )


# ---------------------------------------------------------------------------
# Shared helpers — used by both smoke and e2e suites
# ---------------------------------------------------------------------------

def upload_file(
    filepath: str | Path,
    filename: str | None = None,
    *,
    timeout: int = 30,
) -> str:
    """Upload a file via SAS token and return the ``document_id``.

    1. POST ``/api/upload/sas-token`` to get a signed upload URL.
    2. PUT the file bytes to blob storage via the SAS URL.

    Args:
        filepath: Path to the local file to upload.
        filename: Override the filename sent to the API (defaults to the
            file's actual name).
        timeout: HTTP request timeout in seconds.

    Returns:
        The ``document_id`` string assigned by the API.
    """
    filepath = Path(filepath)
    if filename is None:
        filename = filepath.name

    ext = Path(filename).suffix.lower()
    content_type = _CONTENT_TYPES.get(ext, "application/octet-stream")
    file_bytes = filepath.read_bytes()

    # Step 1 — request a SAS token
    sas_resp = requests.post(
        f"{BASE_URL}/api/upload/sas-token",
        json={
            "filename": filename,
            "content_type": content_type,
            "size_bytes": len(file_bytes),
        },
        timeout=timeout,
    )
    assert sas_resp.status_code == 200, (
        f"SAS token request failed ({sas_resp.status_code}): {sas_resp.text}"
    )
    sas_data = sas_resp.json()
    doc_id: str = sas_data["document_id"]

    # Step 2 — upload the actual file
    upload_resp = requests.put(
        sas_data["upload_url"],
        data=file_bytes,
        headers={
            "x-ms-blob-type": "BlockBlob",
            "Content-Type": content_type,
        },
        timeout=timeout,
    )
    assert upload_resp.status_code == 201, (
        f"Blob upload failed ({upload_resp.status_code}): {upload_resp.text}"
    )
    return doc_id


def wait_for_completion(
    document_id: str,
    *,
    timeout: int = 120,
    poll_interval: float = 2.0,
) -> dict:
    """Poll ``/api/documents/status`` until the document is done.

    Returns the final status JSON when the document reaches ``completed``
    or ``failed``.  Fails the test if the timeout is exceeded.
    """
    deadline = time.time() + timeout
    last_status = "unknown"

    while time.time() < deadline:
        resp = requests.get(
            f"{BASE_URL}/api/documents/status",
            params={"document_id": document_id},
            timeout=30,
        )
        assert resp.status_code == 200, (
            f"Status query failed ({resp.status_code}): {resp.text}"
        )
        data = resp.json()
        last_status = data.get("status", "unknown")
        if last_status in ("completed", "failed"):
            return data
        time.sleep(poll_interval)

    pytest.fail(
        f"Conversion timed out after {timeout}s "
        f"(document_id={document_id}, last status: {last_status})"
    )


def download_html(document_id: str, *, timeout: int = 30) -> str:
    """Download the converted HTML for a completed document.

    Calls ``/api/documents/{document_id}/download``, follows the
    ``html_url`` (or ``download_url``), and returns the HTML string.
    """
    dl_resp = requests.get(
        f"{BASE_URL}/api/documents/{document_id}/download",
        timeout=timeout,
    )
    assert dl_resp.status_code == 200, (
        f"Download endpoint failed ({dl_resp.status_code}): {dl_resp.text}"
    )
    dl_data = dl_resp.json()

    html_url = dl_data.get("download_url") or dl_data.get("html_url")
    assert html_url, "No HTML download URL in response"

    html_resp = requests.get(html_url, timeout=timeout)
    assert html_resp.status_code == 200, (
        f"HTML download failed ({html_resp.status_code})"
    )
    return html_resp.text


def cleanup_document(document_id: str) -> None:
    """Best-effort deletion of a document (ignores errors)."""
    try:
        requests.delete(
            f"{BASE_URL}/api/documents/{document_id}",
            timeout=10,
        )
    except Exception:
        pass
