# Feature Specification: Gap Closure — Entra ID Auth & Health Checks

**Branch**: `005-gap-closure` | **Date**: 2026-03-12 | **Status**: Draft
**Origin**: Batman's delta analysis between Sean's app and Robert's app

## Problem Statement

The WCAG document converter's OCR pipeline uses API key authentication as the
primary method for Azure Document Intelligence. The production worker has an
**expired API key** causing all OCR to fail with HTTP 401, resulting in every
scanned page being flagged `confidence=0.0, needs_review=True`.

Robert's reference application uses Entra ID (managed identity) exclusively —
no API keys. Managed identities don't expire, eliminating this entire class of
outage.

Additionally, the worker has no startup health check for Document Intelligence
connectivity. Auth failures only surface on the first conversion attempt,
making diagnosis slow.

## Gaps Identified

### P0 — Flip OCR Auth to Entra ID Default (Critical)

**File**: `backend/ocr_service.py` (lines 66–83)
**Current**: `_get_client()` checks `DOCUMENT_INTELLIGENCE_KEY` first → API key auth.
Falls back to `DefaultAzureCredential` only if no key is set.
**Target**: Try `DefaultAzureCredential` first. Use API key only as escape hatch.

### P1 — Add DI Connectivity Health Check on Worker Startup

**File**: `app/worker.py`
**Current**: Worker starts polling immediately with no connectivity validation.
**Target**: On startup, test Document Intelligence auth and log the result.

### P2 — Extend Entra ID Pattern to Blob Storage (Future / Deferred)

**Files**: `app/dependencies.py`, `app/config.py`
**Current**: Storage auth already supports both connection strings and
`DefaultAzureCredential` via `AzureWebJobsStorage__accountName`.
**Target**: Evaluate whether connection strings can be fully removed.
**Note**: Deferred — storage auth dual-mode already works correctly.

## Requirements

### Functional

1. `_get_client()` MUST try `DefaultAzureCredential` first
2. `_get_client()` MUST fall back to API key only when `DOCUMENT_INTELLIGENCE_KEY`
   is explicitly set AND `DefaultAzureCredential` is unavailable
3. A WARNING log MUST be emitted when API key fallback is used
4. Worker MUST test DI auth on startup and log success/failure
5. Worker MUST NOT crash if DI is unreachable at startup (log and continue)
6. `DOCUMENT_INTELLIGENCE_KEY` MUST be removed from production env vars

### Non-Functional

1. `backend/` package MUST remain free of Azure Functions SDK dependencies
2. OCR failures MUST remain non-fatal (graceful degradation preserved)
3. All existing tests in `tests/unit/` MUST continue to pass
4. Local dev with Azurite MUST continue to work (OCR requires real Azure)
5. Changes MUST be deployable without coordinated rollout (backwards compatible)

## Constraints

- Constitution Principle VIII mandates `DefaultAzureCredential`
- Constitution Principle III mandates graceful OCR degradation
- The `backend/` package has zero Azure Functions SDK dependencies — keep it
- RBAC role `Cognitive Services User` must be assigned to managed identity
- Bicep infra must be updated to remove `DOCUMENT_INTELLIGENCE_KEY` env var
