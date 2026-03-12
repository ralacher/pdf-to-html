# Quickstart: Gap Closure — Entra ID Auth & Health Checks

**Spec**: [spec.md](spec.md) | **Date**: 2026-03-12

## What Changed

1. **OCR auth priority inverted**: `backend/ocr_service.py` now uses Entra ID
   (`DefaultAzureCredential`) first, API key only as fallback with a WARNING log.
2. **Worker startup health check**: `app/worker.py` tests Document Intelligence
   connectivity on startup and logs the auth method.
3. **RBAC script updated**: `scripts/assign-storage-rbac.sh` now also assigns
   `Cognitive Services User` role to the worker's managed identity for Entra ID
   OCR auth on Document Intelligence.
4. **Bicep updated**: `AZURE_CLIENT_ID` added to shared env vars; no
   `DOCUMENT_INTELLIGENCE_KEY` in IaC.

## Local Development

No changes for local dev. If you have `az login` active, `DefaultAzureCredential`
will use your CLI credentials. If you prefer API key auth:

```bash
# .env
DOCUMENT_INTELLIGENCE_ENDPOINT=https://your-di.cognitiveservices.azure.com/
DOCUMENT_INTELLIGENCE_KEY=your-key-here
```

The health check on worker startup will show:

```
[INFO] Document Intelligence auth OK (method: Entra ID)
```

or, with API key:

```
[WARNING] Document Intelligence auth via API key fallback
```

## Production Deployment

### Step 1: Deploy new code (safe — no behavior change until RBAC assigned)

```bash
# Normal deploy via CI/CD — the code change is backwards compatible
git push origin 005-gap-closure
```

### Step 2: Assign RBAC roles (storage + Document Intelligence)

```bash
# Requires Owner or User Access Administrator on the target resources.
# This script assigns both storage RBAC and Cognitive Services User role
# for Entra ID OCR auth on Document Intelligence.
#
# Override DI defaults via env vars if needed:
#   DI_ACCOUNT_NAME=my-di-resource DI_RESOURCE_GROUP=my-rg bash scripts/assign-storage-rbac.sh
bash scripts/assign-storage-rbac.sh
```

### Step 3: Remove API key from production env vars

```bash
# After verifying Entra ID auth works
az containerapp update \
  --name ca-pdftohtml-worker \
  --resource-group rg-pdftohtml \
  --remove-env-vars DOCUMENT_INTELLIGENCE_KEY
```

### Step 4: Verify

Check worker logs for:
```
[INFO] Document Intelligence auth OK (method: Entra ID)
```

Upload a scanned PDF and verify OCR results have `confidence > 0.0`.

## Running Tests

```bash
# All existing tests must pass
pytest tests/unit/ -v

# New tests for auth inversion and health check
pytest tests/unit/test_ocr_auth.py -v
```

## Files Modified

| File | Change |
|------|--------|
| `backend/ocr_service.py` | Invert auth priority in `_get_client()` |
| `app/worker.py` | Add `_check_di_connectivity()` startup check |
| `infra/modules/container-apps.bicep` | Add `AZURE_CLIENT_ID` env var |
| `scripts/assign-storage-rbac.sh` | UPDATED — DI RBAC for Entra ID OCR |
| `tests/unit/test_ocr_auth.py` | NEW — tests for auth inversion |
| `tests/unit/test_worker_health.py` | NEW — tests for DI health check |
