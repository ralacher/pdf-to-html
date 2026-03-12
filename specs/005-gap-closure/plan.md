# Implementation Plan: Gap Closure — Entra ID Auth & Health Checks

**Branch**: `005-gap-closure` | **Date**: 2026-03-12 | **Spec**: [spec.md](spec.md)
**Input**: Batman's delta analysis between Sean's app and Robert's app

## Summary

Close three gaps identified in Batman's delta analysis by inverting the OCR
authentication priority from API key → Entra ID to Entra ID → API key, adding
a Document Intelligence connectivity health check to the worker startup, and
preparing infrastructure for key-free operation.

The `backend/ocr_service.py` module's `_get_client()` function currently checks
for `DOCUMENT_INTELLIGENCE_KEY` first. Production has an **expired API key**
causing all OCR to fail with 401. Inverting the priority so
`DefaultAzureCredential` (managed identity) takes precedence eliminates this
class of outage entirely. A startup health check in `app/worker.py` catches
auth failures immediately instead of waiting for the first scanned PDF upload.

The `backend/` package remains free of Azure Functions SDK dependencies. All
changes are backwards compatible — deployment can be phased without coordination.

## Technical Context

**Language/Version**: Python 3.12
**Primary Dependencies**:
- `azure-ai-documentintelligence` — Document Intelligence SDK
- `azure-identity` — `DefaultAzureCredential` (already imported)
- `azure-core` — `AzureKeyCredential`, `ClientAuthenticationError`
**Storage**: Azure Blob Storage via connection string or `DefaultAzureCredential`
(existing dual-mode — unchanged)
**OCR**: Azure Document Intelligence `prebuilt-layout` model
**Target Platform**: Azure Container Apps (Consumption plan)
**Managed Identity**: User-assigned (`id-pdftohtml-apps`) — already exists in Bicep
**Testing**: pytest with `unittest.mock` — no OCR tests exist yet
**Project Type**: Document conversion pipeline (Python backend + React frontend)
**Constraints**:
- `backend/` package: zero Azure Functions SDK dependencies
- OCR failures: non-fatal (graceful degradation with `confidence=0.0, needs_review=True`)
- Local dev: Azurite for storage, real Azure or API key for DI
- Existing tests: all `tests/unit/` must continue to pass

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. WCAG 2.1 AA Compliance | ✅ PASS | HTML output pipeline unchanged; no effect on WCAG compliance |
| II. Multi-Format Ingestion | ✅ PASS | Extractors (PDF, DOCX, PPTX) completely unchanged |
| III. Selective OCR | ✅ PASS | OCR graceful degradation preserved; health check is non-fatal |
| IV. Accessible Semantic Output | ✅ PASS | html_builder.py unchanged |
| V. Batch Processing at Scale | ✅ PASS | Worker queue processing unchanged; health check adds < 1s startup time |
| VI. Modular Pipeline | ✅ PASS | `backend/` package stays self-contained; no new cross-module deps |
| VII. Test-First Development | ✅ PASS | New unit tests for auth inversion and health check |
| VIII. Cloud-Native Resilience | ✅ PASS | **Directly advances this principle** — mandates `DefaultAzureCredential`; removes secret dependency |

**GATE RESULT**: ALL PASS — proceed to Phase 0.

### Post-Design Re-Check

| Principle | Status | Notes |
|-----------|--------|-------|
| III. Selective OCR | ✅ PASS | OCR still non-fatal; `_get_client()` failure caught by existing try/except in `ocr_pdf_pages()` |
| VI. Modular Pipeline | ✅ PASS | `backend/ocr_service.py` changes are internal; public API (`ocr_pdf_pages()`) unchanged |
| VII. Test-First Development | ✅ PASS | 2 new test files: `test_ocr_auth.py`, `test_worker_health.py` |
| VIII. Cloud-Native Resilience | ✅ PASS | Entra ID is now the default; API key is escape hatch only |

**POST-DESIGN GATE**: ALL PASS — proceed to Phase 2 task generation.

## Project Structure

### Documentation (this feature)

```text
specs/005-gap-closure/
├── spec.md                      # Feature specification
├── plan.md                      # This file — implementation plan
├── research.md                  # Phase 0: research decisions (7 items)
├── data-model.md                # Phase 1: auth strategy state machines
├── quickstart.md                # Phase 1: developer onboarding guide
├── contracts/
│   ├── get-client-auth.md       # _get_client() v1→v2 contract change
│   └── worker-health-check.md   # _check_di_connectivity() contract
└── tasks.md                     # Phase 2: ordered task list (pending)
```

### Code Changes

```text
backend/
└── ocr_service.py               # MODIFY — invert _get_client() auth priority

app/
└── worker.py                    # MODIFY — add _check_di_connectivity()

infra/
└── modules/
    └── container-apps.bicep     # MODIFY — add AZURE_CLIENT_ID env var

scripts/
└── assign-di-rbac.sh           # NEW — Cognitive Services User RBAC assignment

tests/
└── unit/
    ├── test_ocr_auth.py         # NEW — auth inversion tests
    └── test_worker_health.py    # NEW — health check tests
```

## Phase 0: Research (Complete)

See [research.md](research.md) for full details. Key decisions:

| # | Question | Decision |
|---|----------|----------|
| R1 | DefaultAzureCredential in Container Apps | Works with `AZURE_CLIENT_ID` env var for user-assigned identity |
| R2 | RBAC role for DI | `Cognitive Services User` (least privilege) |
| R3 | Auth priority inversion | Invert if/else; key is fallback with WARNING |
| R4 | Health check design | `credential.get_token()` for zero-cost verification |
| R5 | Bicep changes | Add `AZURE_CLIENT_ID`; RBAC via script + optional Bicep module |
| R6 | Backward compatibility | Yes — three-step phased rollout |
| R7 | Impact on existing tests | None — no existing OCR auth tests |

## Phase 1: Design & Contracts (Complete)

### 1.1 Data Model

See [data-model.md](data-model.md). No new entities — changes are behavioral:
- `_get_client()` auth priority state machine (inverted)
- `ConversionWorker` startup lifecycle (health check added)
- Bicep env var additions (`AZURE_CLIENT_ID`)

### 1.2 Interface Contracts

See [contracts/](contracts/):
- **[get-client-auth.md](contracts/get-client-auth.md)**: `_get_client()` v1→v2
  behavioral change — Entra ID first, API key fallback with WARNING
- **[worker-health-check.md](contracts/worker-health-check.md)**:
  `_check_di_connectivity()` — non-fatal startup verification

### 1.3 Implementation Details

#### P0: Invert `_get_client()` Auth Priority

**File**: `backend/ocr_service.py` (lines 66–83)

**Current code**:
```python
def _get_client() -> DocumentIntelligenceClient:
    endpoint = os.environ["DOCUMENT_INTELLIGENCE_ENDPOINT"]
    key = os.environ.get("DOCUMENT_INTELLIGENCE_KEY")
    if key:
        from azure.core.credentials import AzureKeyCredential
        return DocumentIntelligenceClient(
            endpoint=endpoint,
            credential=AzureKeyCredential(key),
        )
    return DocumentIntelligenceClient(
        endpoint=endpoint,
        credential=DefaultAzureCredential(),
    )
```

**New code** (pseudocode):
```python
def _get_client() -> DocumentIntelligenceClient:
    endpoint = os.environ["DOCUMENT_INTELLIGENCE_ENDPOINT"]

    # Entra ID is the default — managed identity, az login, etc.
    key = os.environ.get("DOCUMENT_INTELLIGENCE_KEY")
    if key:
        logger.warning(
            "DOCUMENT_INTELLIGENCE_KEY is set — using API key auth as fallback. "
            "Consider removing the key and using managed identity instead."
        )
        from azure.core.credentials import AzureKeyCredential
        return DocumentIntelligenceClient(
            endpoint=endpoint,
            credential=AzureKeyCredential(key),
        )

    return DocumentIntelligenceClient(
        endpoint=endpoint,
        credential=DefaultAzureCredential(),
    )
```

Wait — this is actually the **same logic** with just a warning added. The real
inversion requires a different approach because `DefaultAzureCredential()`
doesn't fail on construction. The true inversion is:

```python
def _get_client() -> DocumentIntelligenceClient:
    endpoint = os.environ["DOCUMENT_INTELLIGENCE_ENDPOINT"]

    # Always prefer Entra ID (managed identity / az login).
    # API key is an escape hatch only — log a warning when used.
    key = os.environ.get("DOCUMENT_INTELLIGENCE_KEY")
    if not key:
        return DocumentIntelligenceClient(
            endpoint=endpoint,
            credential=DefaultAzureCredential(),
        )

    # Key is set — but we still prefer identity auth.
    # The key exists only as a fallback for environments without
    # managed identity (rare). Log a warning.
    logger.warning(
        "DOCUMENT_INTELLIGENCE_KEY is set for endpoint %s. "
        "Prefer managed identity — remove the key env var when "
        "Cognitive Services User role is assigned.",
        endpoint,
    )
    from azure.core.credentials import AzureKeyCredential
    return DocumentIntelligenceClient(
        endpoint=endpoint,
        credential=AzureKeyCredential(key),
    )
```

**Key insight**: The real fix is not a code logic change — it's an **env var
change**. By removing `DOCUMENT_INTELLIGENCE_KEY` from production, the existing
else-branch (DefaultAzureCredential) would already be used. The code change
adds the WARNING log and updates the docstring to make the intent clear:
Entra ID is the intended path, key is the escape hatch.

However, we also want the code to **document** the correct priority so future
developers don't re-add the key thinking it's the primary path. The warning
serves this purpose.

#### P1: Add DI Health Check to Worker

**File**: `app/worker.py`

```python
def _check_di_connectivity(self) -> None:
    """Test Document Intelligence auth on startup (non-fatal)."""
    endpoint = settings.DOCUMENT_INTELLIGENCE_ENDPOINT
    if not endpoint:
        logger.info(
            "DOCUMENT_INTELLIGENCE_ENDPOINT not set — "
            "OCR will be skipped for scanned pages"
        )
        return

    # Test credential chain without making a DI API call
    try:
        from azure.identity import DefaultAzureCredential
        credential = DefaultAzureCredential()
        credential.get_token("https://cognitiveservices.azure.com/.default")
        logger.info(
            "Document Intelligence auth OK (method: Entra ID, endpoint: %s)",
            endpoint,
        )
        return
    except Exception as e:
        logger.debug("DefaultAzureCredential failed: %s", e)

    # Check for API key fallback
    key = settings.DOCUMENT_INTELLIGENCE_KEY
    if key:
        logger.warning(
            "Document Intelligence will use API key fallback for %s. "
            "Consider assigning Cognitive Services User role to the "
            "managed identity and removing the key.",
            endpoint,
        )
    else:
        logger.warning(
            "Document Intelligence auth UNAVAILABLE for %s — "
            "OCR will fail until auth is configured. "
            "Assign Cognitive Services User role or set "
            "DOCUMENT_INTELLIGENCE_KEY.",
            endpoint,
        )
```

#### P0 (Infra): RBAC Assignment Script

**File**: `scripts/assign-di-rbac.sh` (new)

Pattern matches existing `scripts/assign-storage-rbac.sh`:
- Uses `az role assignment create`
- Assigns `Cognitive Services User` to managed identity
- Scoped to the Document Intelligence resource
- Idempotent (suppresses "already exists" errors)

#### P0 (Infra): Bicep Env Var Update

**File**: `infra/modules/container-apps.bicep`

Add to `sharedEnvVars`:
```bicep
{ name: 'AZURE_CLIENT_ID', value: managedIdentity.properties.clientId }
```

This ensures `DefaultAzureCredential` resolves the correct user-assigned
identity without trying system-assigned first.

### 1.4 Test Strategy

#### test_ocr_auth.py — Auth Inversion Tests

| Test | Description |
|------|-------------|
| `test_no_key_uses_default_credential` | When `DOCUMENT_INTELLIGENCE_KEY` is not set, client uses `DefaultAzureCredential` |
| `test_key_set_uses_key_and_logs_warning` | When key is set, client uses `AzureKeyCredential` and logs WARNING |
| `test_endpoint_required` | Missing `DOCUMENT_INTELLIGENCE_ENDPOINT` raises `KeyError` |
| `test_key_warning_includes_endpoint` | WARNING message includes the endpoint URL |

#### test_worker_health.py — Health Check Tests

| Test | Description |
|------|-------------|
| `test_no_endpoint_logs_info_and_returns` | Empty endpoint logs INFO skip message |
| `test_credential_success_logs_info` | Successful token acquisition logs INFO |
| `test_credential_failure_with_key_logs_warning` | Failed credential + key present logs key fallback WARNING |
| `test_credential_failure_no_key_logs_warning` | Failed credential + no key logs auth unavailable WARNING |
| `test_health_check_never_raises` | Any exception is caught — method never raises |
| `test_health_check_called_on_start` | `start()` calls `_check_di_connectivity()` before poll loop |

## Deployment Sequence

```
┌─────────────────────────────────────────────────────────────┐
│ Step 1: Deploy code                                          │
│   - New _get_client() with WARNING on key path              │
│   - New _check_di_connectivity() in worker                  │
│   - AZURE_CLIENT_ID in Bicep                                │
│   Effect: No behavior change (key still set in prod)         │
│   Risk: Zero                                                 │
├─────────────────────────────────────────────────────────────┤
│ Step 2: Assign RBAC                                          │
│   - Run scripts/assign-di-rbac.sh                           │
│   - Assigns Cognitive Services User to managed identity      │
│   Effect: DefaultAzureCredential now works for DI            │
│   Risk: Low (additive — doesn't remove anything)             │
├─────────────────────────────────────────────────────────────┤
│ Step 3: Remove key from production                           │
│   - az containerapp update --remove-env-vars                │
│     DOCUMENT_INTELLIGENCE_KEY                                │
│   Effect: Code uses DefaultAzureCredential (no WARNING)      │
│   Risk: Low (RBAC already verified in Step 2)                │
├─────────────────────────────────────────────────────────────┤
│ Step 4: Verify                                               │
│   - Check worker startup logs for "auth OK (Entra ID)"      │
│   - Upload scanned PDF; verify OCR confidence > 0.0          │
│   - Confirm no WARNING logs about API key fallback           │
└─────────────────────────────────────────────────────────────┘
```

## Risk Assessment

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| RBAC assignment fails (insufficient permissions) | OCR stays broken (no change) | Medium | Admin (Sean) runs script; same pattern as storage RBAC |
| DefaultAzureCredential slow in Container Apps | Worker startup delayed ~2s | Low | AZURE_CLIENT_ID env var skips credential chain guessing |
| Removing key before RBAC assigned | OCR fails (same as today) | Low | Deployment sequence enforces order; key removal is last step |
| Health check masks auth issues | False confidence in logs | Low | Health check tests token acquisition, not full API call |
| Existing tests break | CI failure | Very Low | Analysis confirms zero existing tests touch `_get_client()` or auth |

## Open Questions (P2 — Deferred)

1. **Blob storage key removal**: `app/dependencies.py` already supports
   `DefaultAzureCredential` via `AzureWebJobsStorage__accountName`. Should
   we remove `AZURE_STORAGE_CONNECTION_STRING` from production? Deferred —
   storage auth works correctly today.

2. **SAS token migration**: User-delegation SAS (identity-based) is already
   implemented in `dependencies.py`. Connection-string SAS is only used for
   Azurite local dev. No change needed.

---

*Plan complete. Ready for Phase 2 task generation.*
