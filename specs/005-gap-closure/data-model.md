# Data Model: Gap Closure — Entra ID Auth & Health Checks

**Spec**: [spec.md](spec.md) | **Date**: 2026-03-12

## Overview

This feature does not introduce new data entities. It modifies the
**authentication strategy** for existing Azure SDK clients and adds a
**startup health check** to the worker. The data model impact is limited
to configuration changes and behavioral contract changes.

## Modified Entities

### 1. `_get_client()` — Auth Strategy (backend/ocr_service.py)

**Current behavior** (lines 66–83):
```
IF DOCUMENT_INTELLIGENCE_KEY is set
  → AzureKeyCredential (API key)
ELSE
  → DefaultAzureCredential (Entra ID)
```

**New behavior**:
```
ALWAYS → DefaultAzureCredential (Entra ID)
IF DefaultAzureCredential fails AND DOCUMENT_INTELLIGENCE_KEY is set
  → AzureKeyCredential (API key) + WARNING log
ELSE IF DefaultAzureCredential fails AND no key
  → raise (let caller handle graceful degradation)
```

**State transitions**:
```
┌─────────────────┐
│  _get_client()  │
│    called       │
└───────┬─────────┘
        │
        ▼
┌───────────────────────┐
│ Try DefaultAzure-     │
│ Credential            │
└───────┬───────────────┘
        │
   ┌────┴────┐
   │ Success │────────────► Return client (Entra ID)
   └─────────┘
        │
   ┌────┴────┐
   │ Failed  │
   └────┬────┘
        │
        ▼
┌───────────────────────┐
│ DOCUMENT_INTELLIGENCE │
│ _KEY set?             │
└───────┬───────────────┘
        │
   ┌────┴────┐
   │   Yes   │────► Log WARNING ──► Return client (API key)
   └─────────┘
        │
   ┌────┴────┐
   │   No    │────► Raise ClientAuthenticationError
   └─────────┘
```

### 2. `ConversionWorker` — Startup Lifecycle (app/worker.py)

**Current lifecycle**:
```
__init__ → start() → [poll loop] → stop()
```

**New lifecycle**:
```
__init__ → start() → _check_di_connectivity() → [poll loop] → stop()
```

**Health check states**:
```
┌──────────────────────┐
│ _check_di_            │
│ connectivity()        │
└───────┬──────────────┘
        │
        ▼
┌───────────────────────┐
│ get_token(cognitive-  │
│ services scope)       │
└───────┬───────────────┘
        │
   ┌────┴────┐
   │ Success │────► log INFO "DI auth OK (Entra ID)"
   └─────────┘
        │
   ┌────┴────┐
   │ Failed  │
   └────┬────┘
        │
        ▼
┌───────────────────────┐
│ DOCUMENT_INTELLIGENCE │
│ _KEY set?             │
└───────┬───────────────┘
   ┌────┴────┐
   │   Yes   │────► log WARNING "DI auth via API key (fallback)"
   └─────────┘
   ┌────┴────┐
   │   No    │────► log WARNING "DI auth UNAVAILABLE — OCR disabled"
   └─────────┘
        │
        ▼
   [continue to poll loop — non-fatal]
```

### 3. Settings — Configuration (app/config.py)

**No new fields added.** Existing fields are sufficient:

| Field | Type | Default | Status |
|-------|------|---------|--------|
| `DOCUMENT_INTELLIGENCE_ENDPOINT` | `str` | `""` | Unchanged |
| `DOCUMENT_INTELLIGENCE_KEY` | `str` | `""` | Unchanged (but removed from prod env) |
| `AZURE_CLIENT_ID` | — | — | Set via Bicep env var, not in Settings |

**Note**: `AZURE_CLIENT_ID` is consumed directly by `DefaultAzureCredential`
from the Azure Identity SDK. It does not need to be in the `Settings` class.

### 4. Infrastructure — RBAC Assignments

**New role assignment** (not a data model, but a required state change):

| Principal | Role | Scope |
|-----------|------|-------|
| `id-pdftohtml-apps` (managed identity) | `Cognitive Services User` | Document Intelligence resource |

**Env var changes in Bicep** (`sharedEnvVars`):

| Variable | Action |
|----------|--------|
| `AZURE_CLIENT_ID` | ADD — set to managed identity client ID |
| `DOCUMENT_INTELLIGENCE_KEY` | OMIT — never set in Bicep (was manual) |

## Validation Rules

1. `DOCUMENT_INTELLIGENCE_ENDPOINT` must be a valid HTTPS URL when DI is needed
2. `DefaultAzureCredential` must resolve before API key fallback is attempted
3. Health check must complete within 10 seconds (timeout for token acquisition)
4. API key WARNING must include the endpoint URL for debugging

## Relationships

```
Settings ──reads──► _get_client() ──creates──► DocumentIntelligenceClient
                                                      │
ConversionWorker.start()                              │
    │                                                 │
    ├── _check_di_connectivity() ──verifies──► credential chain
    │                                                 │
    └── _poll_once() ──► _convert() ──► ocr_pdf_pages() ──uses──┘
```
