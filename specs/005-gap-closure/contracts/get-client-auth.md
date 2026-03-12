# Contract: `_get_client()` Auth Strategy

**File**: `backend/ocr_service.py`
**Function**: `_get_client() -> DocumentIntelligenceClient`

## Current Contract (v1 — API Key Priority)

```python
def _get_client() -> DocumentIntelligenceClient:
    """
    Env vars required:
      - DOCUMENT_INTELLIGENCE_ENDPOINT (always)
      - DOCUMENT_INTELLIGENCE_KEY (optional — triggers API key auth)
    
    Priority:
      1. API key (if DOCUMENT_INTELLIGENCE_KEY is set)
      2. DefaultAzureCredential (fallback)
    
    Raises:
      KeyError — if DOCUMENT_INTELLIGENCE_ENDPOINT not set
      ClientAuthenticationError — if neither auth method works
    """
```

## New Contract (v2 — Entra ID Priority)

```python
def _get_client() -> DocumentIntelligenceClient:
    """Create a Document Intelligence client.

    Uses Entra ID via DefaultAzureCredential by default. Falls back to
    API key (DOCUMENT_INTELLIGENCE_KEY) only when identity auth is
    unavailable.

    Env vars:
      - DOCUMENT_INTELLIGENCE_ENDPOINT (required)
      - DOCUMENT_INTELLIGENCE_KEY (optional — escape-hatch fallback)
      - AZURE_CLIENT_ID (optional — disambiguates user-assigned identity)

    Auth priority:
      1. DefaultAzureCredential (Entra ID / managed identity / az login)
      2. API key (only if key is set — logs WARNING)

    Raises:
      KeyError — if DOCUMENT_INTELLIGENCE_ENDPOINT not set
      ClientAuthenticationError — if no auth method succeeds

    Logging:
      WARNING — when falling back to API key auth
      DEBUG — when using DefaultAzureCredential successfully
    """
```

## Behavioral Changes

| Aspect | v1 (current) | v2 (new) |
|--------|-------------|----------|
| Auth priority | Key first | Credential first |
| Stale key behavior | Silent 401 failure | Ignored (credential used) |
| Missing key + no identity | Works (credential used) | Same |
| Key set + identity works | Uses key (wastes identity) | Uses identity |
| Key set + identity fails | Uses key | Uses key + WARNING |
| No key + no identity | Raises | Same |
| Logging | None | WARNING on key fallback |

## Backward Compatibility

- **Callers**: `ocr_pdf_pages()` is the only caller. It wraps the entire
  DI call in a try/except that returns `OcrPageResult(confidence=0.0,
  needs_review=True)` on failure. No caller changes needed.
- **Env vars**: `DOCUMENT_INTELLIGENCE_KEY` continues to work when set.
  No env var removed from the code — only from production deployment config.
- **Return type**: Unchanged (`DocumentIntelligenceClient`).
