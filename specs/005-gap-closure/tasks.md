# Tasks: Gap Closure — Entra ID Auth & Health Checks

**Feature**: Entra ID Auth Inversion & DI Health Check
**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)
**Branch**: `004-container-apps-migration`
**Generated**: 2026-03-12

## Overview

Three priorities from Batman's delta analysis:
- **P0**: Flip OCR auth in `backend/ocr_service.py` to prefer `DefaultAzureCredential` over API keys
- **P1**: Add DI connectivity health check in `app/worker.py` on startup
- **P2**: Deferred (blob storage Entra ID) — documented as future work only

Total: **14 tasks** across 5 phases.

---

## Phase 1 — Setup

> Project-level scaffolding and infrastructure prerequisites.

- [ ] T001 Add `AZURE_CLIENT_ID` env var to `sharedEnvVars` in `infra/modules/container-apps.bicep` — set value to `managedIdentity.properties.clientId` so `DefaultAzureCredential` resolves the user-assigned identity deterministically
- [ ] T002 Create RBAC assignment script `scripts/assign-di-rbac.sh` — assign `Cognitive Services User` role (ID `a97b65f3-24c7-4388-baec-2e87135dc908`) to managed identity `id-pdftohtml-apps` scoped to the Document Intelligence resource; follow the pattern established in `scripts/assign-storage-rbac.sh` (idempotent, `set -euo pipefail`, suppress "already exists" errors)

## Phase 2 — Foundational

> Blocking prerequisites that must be verified before user-story implementation.

- [ ] T003 Run existing test suite with `pytest tests/unit/ -v` and confirm all tests pass — this is the baseline before any code changes
- [ ] T004 [P] Verify `backend/ocr_service.py` has no Azure Functions SDK imports by scanning for `azure.functions` or `func` imports — confirm the zero-dependency constraint is met before modifying the file

## Phase 3 — P0: Invert OCR Auth Priority (US1)

> **Goal**: `_get_client()` in `backend/ocr_service.py` uses `DefaultAzureCredential` by default; API key is escape-hatch fallback with WARNING log.
>
> **Acceptance**: When `DOCUMENT_INTELLIGENCE_KEY` is unset, client is constructed with `DefaultAzureCredential`. When key is set, client uses `AzureKeyCredential` and a WARNING is logged that includes the endpoint URL. Missing `DOCUMENT_INTELLIGENCE_ENDPOINT` raises `KeyError`. All existing tests continue to pass.

- [ ] T005 [US1] Create unit test file `tests/unit/test_ocr_auth.py` with four tests per plan §1.4: (1) `test_no_key_uses_default_credential` — patch `os.environ` with no key, assert `DocumentIntelligenceClient` called with `DefaultAzureCredential` instance; (2) `test_key_set_uses_key_and_logs_warning` — set `DOCUMENT_INTELLIGENCE_KEY`, assert `AzureKeyCredential` used and WARNING logged; (3) `test_endpoint_required` — remove `DOCUMENT_INTELLIGENCE_ENDPOINT`, assert `KeyError`; (4) `test_key_warning_includes_endpoint` — assert WARNING message contains the endpoint URL. Use `unittest.mock.patch` for env vars and SDK constructors.
- [ ] T006 [US1] Modify `_get_client()` in `backend/ocr_service.py` (lines 66–83) — invert auth priority per contract `contracts/get-client-auth.md` v2: always construct with `DefaultAzureCredential` when `DOCUMENT_INTELLIGENCE_KEY` is not set; when key IS set, log `logger.warning()` with endpoint URL then construct with `AzureKeyCredential`. Update docstring to document Entra ID priority, env vars (`DOCUMENT_INTELLIGENCE_ENDPOINT`, `DOCUMENT_INTELLIGENCE_KEY`, `AZURE_CLIENT_ID`), and logging behavior.
- [ ] T007 [US1] Run `pytest tests/unit/test_ocr_auth.py -v` to verify all four new auth tests pass
- [ ] T008 [US1] Run `pytest tests/unit/ -v` to confirm zero regressions in existing test suite after `_get_client()` modification

## Phase 4 — P1: Worker DI Health Check (US2)

> **Goal**: `ConversionWorker` in `app/worker.py` tests Document Intelligence auth on startup and logs the result before entering the poll loop.
>
> **Acceptance**: Worker startup logs one of: INFO "auth OK (Entra ID)", WARNING "API key fallback", WARNING "auth UNAVAILABLE", or INFO "not configured". Health check never raises. All existing tests continue to pass.

- [ ] T009 [US2] Create unit test file `tests/unit/test_worker_health.py` with six tests per plan §1.4: (1) `test_no_endpoint_logs_info_and_returns` — empty endpoint logs INFO skip; (2) `test_credential_success_logs_info` — successful `get_token()` logs INFO; (3) `test_credential_failure_with_key_logs_warning` — failed credential + key present logs fallback WARNING; (4) `test_credential_failure_no_key_logs_warning` — failed credential + no key logs unavailable WARNING; (5) `test_health_check_never_raises` — any exception is caught, method returns `None`; (6) `test_health_check_called_on_start` — verify `start()` calls `_check_di_connectivity()` before poll loop. Mock `DefaultAzureCredential`, `settings`, and signal handlers.
- [ ] T010 [US2] Add `_check_di_connectivity(self) -> None` method to `ConversionWorker` class in `app/worker.py` per contract `contracts/worker-health-check.md`: check `settings.DOCUMENT_INTELLIGENCE_ENDPOINT`, attempt `DefaultAzureCredential().get_token("https://cognitiveservices.azure.com/.default")`, log result, catch all exceptions. Method must never raise.
- [ ] T011 [US2] Insert `self._check_di_connectivity()` call in `ConversionWorker.start()` in `app/worker.py` (line 66) — between signal handler registration and the "Worker started" log message, before the poll loop
- [ ] T012 [US2] Run `pytest tests/unit/test_worker_health.py -v` to verify all six new health check tests pass
- [ ] T013 [US2] Run `pytest tests/unit/ -v` to confirm zero regressions in existing test suite after worker modification

## Phase 5 — Polish & Cross-Cutting Concerns

> Final validation, documentation of deferred work, and full regression check.

- [ ] T014 Document P2 (blob storage Entra ID) as deferred future work — add a comment block at the top of `app/dependencies.py` noting that `AZURE_STORAGE_CONNECTION_STRING` can be replaced with identity-based auth via `AzureWebJobsStorage__accountName` (already supported), and reference this spec (`specs/005-gap-closure/spec.md` §P2) for tracking

---

## Dependency Graph

```
T001 ─┐
T002 ─┤ (no deps — setup tasks, parallelizable)
      │
T003 ─┤ (baseline test run — blocks all code changes)
T004 ─┘
      │
      ▼
┌─────────────────────────────────────────────┐
│ Phase 3 — US1: OCR Auth Inversion (P0)      │
│                                             │
│  T005 (write tests)                         │
│    └──► T006 (implement _get_client v2)     │
│           ├──► T007 (run new tests)         │
│           └──► T008 (full regression)       │
└─────────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────┐
│ Phase 4 — US2: Worker Health Check (P1)     │
│                                             │
│  T009 (write tests)                         │
│    └──► T010 (implement health check)       │
│           └──► T011 (wire into start())     │
│                  ├──► T012 (run new tests)  │
│                  └──► T013 (full regression)│
└─────────────────────────────────────────────┘
      │
      ▼
T014  (polish — deferred P2 documentation)
```

## Parallel Execution Opportunities

### Within Phase 1 (Setup)
- **T001** and **T002** can run in parallel — different files (`container-apps.bicep` vs `assign-di-rbac.sh`)

### Within Phase 2 (Foundational)
- **T003** and **T004** can run in parallel — T003 runs tests, T004 is a read-only scan

### Across Phases 3 & 4
- Phases 3 and 4 are **independent** — US1 (`backend/ocr_service.py`) and US2 (`app/worker.py`) touch different files with no cross-dependencies. They CAN execute in parallel after Phase 2 completes.

### Within Each User Story
- Test-writing tasks (T005, T009) can start immediately within their phase
- Implementation tasks depend on their test tasks (TDD flow)
- Regression runs (T008, T013) depend on implementation tasks

## Implementation Strategy

### MVP Scope
**US1 (Phase 3) alone is a valid MVP** — flipping the auth priority in `_get_client()` directly fixes the production outage caused by the expired API key. The health check (US2) is valuable but not blocking.

### Incremental Delivery
1. **Increment 1**: T001–T008 (Setup + US1) — OCR auth fixed in production
2. **Increment 2**: T009–T013 (US2) — Health check for early failure detection
3. **Increment 3**: T014 (Polish) — Future work documented

### Deployment Sequence (Post-Merge)
Per plan.md §Deployment Sequence:
1. Deploy new code (backwards compatible — no behavior change until RBAC assigned)
2. Run `scripts/assign-di-rbac.sh` (assigns Cognitive Services User role)
3. Remove `DOCUMENT_INTELLIGENCE_KEY` from production env vars
4. Verify worker logs show "auth OK (Entra ID)"

### Constraints Enforced
- `backend/` package: zero Azure Functions SDK dependencies (verified in T004)
- All `tests/unit/` must pass (verified in T003, T008, T013)
- OCR failures remain non-fatal (graceful degradation preserved)
- Branch: `004-container-apps-migration`
