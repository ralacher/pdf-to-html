# Contract: Worker Startup Health Check

**File**: `app/worker.py`
**Method**: `ConversionWorker._check_di_connectivity()`

## New Contract

```python
def _check_di_connectivity(self) -> None:
    """Test Document Intelligence auth on worker startup.

    Verifies that the credential chain can obtain a token for the
    Cognitive Services scope. Logs the result but NEVER raises — the
    worker must start even if DI is unavailable (OCR is non-fatal).

    Env vars consulted:
      - DOCUMENT_INTELLIGENCE_ENDPOINT — if empty, logs INFO and skips
      - DOCUMENT_INTELLIGENCE_KEY — logged if used as fallback

    Logging:
      INFO  — "Document Intelligence auth OK (method: Entra ID)"
      INFO  — "Document Intelligence not configured — OCR will be skipped"
      WARNING — "Document Intelligence auth failed — OCR will be unavailable
                 until connectivity is restored"
      WARNING — "Document Intelligence auth via API key fallback — consider
                 switching to managed identity"

    Side effects:
      None — purely diagnostic. Does not cache the client or credential.

    Performance:
      Completes within 10 seconds (token acquisition timeout). Does not
      make any Document Intelligence API calls (zero cost).
    """
```

## Integration Point

Called once from `ConversionWorker.start()`, between signal registration and
the poll loop:

```python
def start(self) -> None:
    self._running = True
    signal.signal(signal.SIGTERM, self._handle_signal)
    signal.signal(signal.SIGINT, self._handle_signal)

    self._check_di_connectivity()  # ← NEW

    logger.info("Worker started — polling queue '%s' every %ds", ...)
    while self._running:
        ...
```

## Behavioral Guarantees

1. **Never crashes**: All exceptions caught and logged
2. **Never blocks**: 10-second timeout on token acquisition
3. **Never costs money**: No DI API calls, only token verification
4. **Idempotent**: Can be called multiple times safely
5. **No side effects**: Does not modify worker state or cache credentials
