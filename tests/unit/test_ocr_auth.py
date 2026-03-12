"""
Unit tests for OCR service authentication — _get_client().

Validates that _get_client() prefers Entra ID (DefaultAzureCredential) by
default and only falls back to API key when DOCUMENT_INTELLIGENCE_KEY is set.

Covers:
  - DefaultAzureCredential used when no key env var is present
  - AzureKeyCredential used when DOCUMENT_INTELLIGENCE_KEY is set
  - WARNING logged on API key fallback
  - KeyError raised when DOCUMENT_INTELLIGENCE_ENDPOINT is missing
"""

import logging
import os
from unittest.mock import patch, MagicMock

import pytest

from backend.ocr_service import _get_client


_ENDPOINT = "https://test.cognitiveservices.azure.com/"

# Minimal env that supplies only the endpoint (no key)
_ENV_NO_KEY = {
    "DOCUMENT_INTELLIGENCE_ENDPOINT": _ENDPOINT,
}

# Env with both endpoint and key
_ENV_WITH_KEY = {
    "DOCUMENT_INTELLIGENCE_ENDPOINT": _ENDPOINT,
    "DOCUMENT_INTELLIGENCE_KEY": "test-key",
}


class TestGetClientDefaultCredential:
    """When no API key is configured, Entra ID (DefaultAzureCredential) is used."""

    @patch("backend.ocr_service.DefaultAzureCredential")
    @patch("backend.ocr_service.DocumentIntelligenceClient")
    @patch.dict(os.environ, _ENV_NO_KEY, clear=True)
    def test_get_client_uses_default_credential_when_no_key(
        self, mock_client_cls, mock_cred_cls
    ):
        mock_cred = MagicMock()
        mock_cred_cls.return_value = mock_cred

        _get_client()

        mock_cred_cls.assert_called_once()
        mock_client_cls.assert_called_once_with(
            endpoint=_ENDPOINT,
            credential=mock_cred,
        )


class TestGetClientApiKey:
    """When DOCUMENT_INTELLIGENCE_KEY is set, API key auth is used."""

    @patch("backend.ocr_service.DocumentIntelligenceClient")
    @patch("azure.core.credentials.AzureKeyCredential")
    @patch.dict(os.environ, _ENV_WITH_KEY, clear=True)
    def test_get_client_uses_api_key_when_key_set(
        self, mock_key_cred_cls, mock_client_cls
    ):
        mock_cred = MagicMock()
        mock_key_cred_cls.return_value = mock_cred

        _get_client()

        mock_key_cred_cls.assert_called_once_with("test-key")
        mock_client_cls.assert_called_once_with(
            endpoint=_ENDPOINT,
            credential=mock_cred,
        )


class TestGetClientLogging:
    """Verify appropriate log messages are emitted."""

    @patch("backend.ocr_service.DocumentIntelligenceClient")
    @patch("azure.core.credentials.AzureKeyCredential")
    @patch.dict(os.environ, _ENV_WITH_KEY, clear=True)
    def test_get_client_logs_warning_when_api_key_used(
        self, mock_key_cred_cls, mock_client_cls, caplog
    ):
        with caplog.at_level(logging.WARNING, logger="backend.ocr_service"):
            _get_client()

        assert any(
            "Using API key for Document Intelligence" in record.message
            for record in caplog.records
        ), f"Expected warning about API key usage, got: {[r.message for r in caplog.records]}"


class TestGetClientMissingEndpoint:
    """When DOCUMENT_INTELLIGENCE_ENDPOINT is not set, a KeyError is raised."""

    @patch.dict(os.environ, {}, clear=True)
    def test_get_client_raises_when_no_endpoint(self):
        with pytest.raises(KeyError, match="DOCUMENT_INTELLIGENCE_ENDPOINT"):
            _get_client()
