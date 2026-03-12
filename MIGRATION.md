# Migration Guide: Azure Functions → Azure Container Apps

## Overview

This project has been migrated from **Azure Functions (Python v2)** to **Azure Container Apps** with a FastAPI-based backend and a standalone queue worker. The migration improves local development experience, eliminates cold-start latency, and provides full control over the runtime environment.

## Architecture Changes

| Component | Before (Azure Functions) | After (Container Apps) |
|-----------|--------------------------|------------------------|
| **HTTP API** | `function_app.py` (Azure Functions SDK) | `app/main.py` (FastAPI + Uvicorn) |
| **Queue Processing** | Blob trigger in `function_app.py` | `app/worker.py` (polling Azure Storage Queue) |
| **Configuration** | `host.json` + `local.settings.json` | `app/config.py` (Pydantic Settings) + env vars |
| **Local Dev** | `func start` + Azurite | `docker-compose up` (Azurite + backend + worker + frontend) |
| **Container** | Azure Functions base image | Custom `Dockerfile.backend` (Python 3.12-slim) |
| **Infrastructure** | N/A (portal-deployed) | `infra/` Bicep modules |

## What Changed

### New Files
- `app/main.py` — FastAPI application with all HTTP endpoints
- `app/worker.py` — Queue-based conversion worker
- `app/config.py` — Centralised Pydantic Settings configuration
- `app/dependencies.py` — Shared Azure SDK helpers
- `app/security.py` — Password-protection detection
- `app/__main__.py` — Entrypoint for `python -m app`
- `Dockerfile.backend` — Production container image
- `docker-compose.yml` — Local development orchestration
- `infra/` — Bicep IaC for Azure Container Apps

### Deprecated Files (kept for reference)
- `function_app.py` — Legacy Azure Functions entry point
- `host.json` — Azure Functions host configuration
- `local.settings.json` — Azure Functions local settings

### Unchanged
- `backend/` — All extractors (PDF, DOCX, PPTX), OCR service, HTML builder, WCAG validator
- `frontend/` — Next.js UI (only backend URL default updated)
- `tests/` — Full test suite

## Local Development

### Recommended: Docker Compose

```bash
# Start all services (Azurite, backend API, worker, frontend)
docker-compose up --build

# Services:
#   Frontend:  http://localhost:3000
#   Backend:   http://localhost:8000
#   Azurite:   http://localhost:10000 (blob), 10001 (queue), 10002 (table)
```

### Alternative: Manual Setup

```bash
# Terminal 1: Start Azurite
azurite --loose --skipApiVersionCheck

# Terminal 2: Start FastAPI backend
export AZURE_STORAGE_CONNECTION_STRING="UseDevelopmentStorage=true"
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 3: Start conversion worker
export AZURE_STORAGE_CONNECTION_STRING="UseDevelopmentStorage=true"
python -m app.worker

# Terminal 4: Start frontend
cd frontend && npm run dev
```

## Deployment

### Azure Container Apps (Bicep)

```bash
# Deploy infrastructure
az deployment group create \
  --resource-group rg-pdf-to-html \
  --template-file infra/main.bicep \
  --parameters infra/main.bicepparam
```

See `infra/README.md` for full deployment instructions.

## API Endpoint Mapping

| Endpoint | Azure Functions Route | Container Apps Route |
|----------|----------------------|---------------------|
| Upload SAS token | `POST /api/upload/sas-token` | `POST /api/upload/sas-token` |
| Document status | `GET /api/documents/status` | `GET /api/documents/status` |
| Download document | `GET /api/documents/{id}/download` | `GET /api/documents/{id}/download` |
| Delete document | `DELETE /api/documents/{id}` | `DELETE /api/documents/{id}` |
| Bulk delete | `DELETE /api/documents` | `DELETE /api/documents` |
| Health probe | N/A | `GET /health` |
| Readiness probe | N/A | `GET /ready` |

All `/api/*` routes maintain backward compatibility. The frontend requires no API changes.

## Rollback Procedure

If issues arise with the Container Apps deployment:

1. **Immediate rollback** — Re-deploy the Azure Functions app from the last known-good deployment:
   ```bash
   # The legacy function_app.py is still in the repo
   func azure functionapp publish <app-name>
   ```

2. **Frontend rollback** — Revert `frontend/next.config.mjs` backend URL to `http://localhost:7071`

3. **DNS/Traffic** — If using Azure Front Door or Traffic Manager, shift traffic back to the Functions endpoint

4. **Verify** — Run the migration verification script:
   ```bash
   ./scripts/migrate-verify.sh
   ```

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `AZURE_STORAGE_CONNECTION_STRING` | Yes | `UseDevelopmentStorage=true` | Azure Storage connection |
| `OUTPUT_CONTAINER` | No | `converted` | Output blob container name |
| `INPUT_CONTAINER` | No | `files` | Input blob container name |
| `QUEUE_NAME` | No | `conversion-jobs` | Azure Storage Queue name |
| `LOG_LEVEL` | No | `INFO` | Logging level |
| `PORT` | No | `8000` | HTTP server port |
| `WORKER_MODE` | No | `false` | Run as queue worker instead of HTTP server |
| `DOCUMENT_INTELLIGENCE_ENDPOINT` | No | — | Azure Document Intelligence endpoint (OCR) |
| `DOCUMENT_INTELLIGENCE_KEY` | No | — | Azure Document Intelligence key (OCR) |

## Reference

- [Migration Plan](specs/004-container-apps-migration/plan.md)
- [Infrastructure README](infra/README.md)
- [API Contracts](specs/001-sean/contracts/)
