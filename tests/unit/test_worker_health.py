"""Tests for ConversionWorker._check_di_connectivity startup health check."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest

from app.worker import ConversionWorker


@pytest.fixture()
def worker() -> ConversionWorker:
    """Return a fresh ConversionWorker instance."""
    return ConversionWorker()


# -- 1. Entra ID auth success ------------------------------------------------


def test_di_check_logs_ok_with_entra_id(
    worker: ConversionWorker, caplog: pytest.LogCaptureFixture
) -> None:
    """Endpoint set, no key → client succeeds → logs OK with Entra ID."""
    env = {
        "DOCUMENT_INTELLIGENCE_ENDPOINT": "https://di.cognitiveservices.azure.com",
    }
    with (
        patch.dict("os.environ", env, clear=False),
        patch("backend.ocr_service._get_client", return_value=MagicMock()),
        caplog.at_level(logging.INFO),
    ):
        # Remove the key if it happens to be set in the test environment
        with patch.dict("os.environ", {"DOCUMENT_INTELLIGENCE_KEY": ""}, clear=False):
            import os
            os.environ.pop("DOCUMENT_INTELLIGENCE_KEY", None)
            worker._check_di_connectivity()

    assert any(
        "Document Intelligence connectivity OK" in msg
        and "Entra ID" in msg
        for msg in caplog.messages
    ), f"Expected Entra ID OK log, got: {caplog.messages}"


# -- 2. API key auth success --------------------------------------------------


def test_di_check_logs_ok_with_api_key(
    worker: ConversionWorker, caplog: pytest.LogCaptureFixture
) -> None:
    """Endpoint and key both set → client succeeds → logs OK with API key."""
    env = {
        "DOCUMENT_INTELLIGENCE_ENDPOINT": "https://di.cognitiveservices.azure.com",
        "DOCUMENT_INTELLIGENCE_KEY": "test-key-abc123",
    }
    with (
        patch.dict("os.environ", env, clear=False),
        patch("backend.ocr_service._get_client", return_value=MagicMock()),
        caplog.at_level(logging.INFO),
    ):
        worker._check_di_connectivity()

    assert any(
        "Document Intelligence connectivity OK" in msg
        and "API key" in msg
        for msg in caplog.messages
    ), f"Expected API key OK log, got: {caplog.messages}"


# -- 3. Client creation failure → warning, no raise --------------------------


def test_di_check_logs_warning_on_failure(
    worker: ConversionWorker, caplog: pytest.LogCaptureFixture
) -> None:
    """Endpoint set, client creation raises → logs warning, does NOT raise."""
    env = {
        "DOCUMENT_INTELLIGENCE_ENDPOINT": "https://di.cognitiveservices.azure.com",
    }
    with (
        patch.dict("os.environ", env, clear=False),
        patch(
            "backend.ocr_service._get_client",
            side_effect=RuntimeError("auth failed"),
        ),
        caplog.at_level(logging.WARNING),
    ):
        # Must NOT raise
        worker._check_di_connectivity()

    assert any(
        "connectivity check failed" in msg and "auth failed" in msg
        for msg in caplog.messages
    ), f"Expected warning log, got: {caplog.messages}"


# -- 4. Endpoint not configured → info, no raise -----------------------------


def test_di_check_logs_info_when_not_configured(
    worker: ConversionWorker, caplog: pytest.LogCaptureFixture
) -> None:
    """No endpoint env var → logs 'not configured' info, does NOT raise."""
    env: dict[str, str] = {}
    with (
        patch.dict(
            "os.environ",
            env,
            clear=False,
        ),
        caplog.at_level(logging.INFO),
    ):
        # Remove both vars so the check sees "not configured"
        import os

        os.environ.pop("DOCUMENT_INTELLIGENCE_ENDPOINT", None)
        os.environ.pop("DOCUMENT_INTELLIGENCE_KEY", None)

        worker._check_di_connectivity()

    assert any(
        "not configured" in msg for msg in caplog.messages
    ), f"Expected 'not configured' log, got: {caplog.messages}"
