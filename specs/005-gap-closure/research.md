# Research: Gap Closure — Entra ID Auth & Health Checks

**Spec**: [spec.md](spec.md) | **Date**: 2026-03-12

## Research Items

### R1: DefaultAzureCredential Behavior in Container Apps

**Question**: How does `DefaultAzureCredential` resolve in Azure Container Apps
with a user-assigned managed identity? Does it auto-detect or need config?

**Decision**: `DefaultAzureCredential` works out of the box with user-assigned
managed identities in Container Apps, but needs the `AZURE_CLIENT_ID` env var
set to the managed identity's client ID when multiple identities are present.
Our Bicep template creates a single user-assigned identity (`id-pdftohtml-apps`)
so we should set `AZURE_CLIENT_ID` explicitly for deterministic resolution.

**Rationale**: The `DefaultAzureCredential` chain tries (in order):
1. EnvironmentCredential (SPN env vars)
2. WorkloadIdentityCredential
3. ManagedIdentityCredential (system-assigned first, then user-assigned)
4. AzureCliCredential (dev only)

With a user-assigned identity, omitting `AZURE_CLIENT_ID` can cause the chain
to try system-assigned first and fail with a confusing error before falling
back. Setting it explicitly avoids this latency and makes auth deterministic.

**Alternatives considered**:
- `ManagedIdentityCredential(client_id=...)` directly — too specific, breaks
  local dev with `az login`
- System-assigned identity — less portable across Container Apps; harder to
  pre-assign RBAC before deployment

### R2: Cognitive Services User RBAC Role

**Question**: What RBAC role does the managed identity need for Document
Intelligence, and at what scope?

**Decision**: Assign `Cognitive Services User` role (built-in role ID:
`a97b65f3-24c7-4388-baec-2e87135dc908`) scoped to the Document Intelligence
resource.

**Rationale**: This is the least-privilege role that grants access to the
Document Intelligence API. `Cognitive Services Contributor` would also work but
grants management-plane access (create/delete resources) which violates
least-privilege.

**Alternatives considered**:
- `Cognitive Services Contributor` — over-privileged
- Custom role — unnecessary; built-in role matches exactly

### R3: Auth Priority Inversion Pattern

**Question**: What's the safest way to invert `_get_client()` auth priority
without breaking local dev or existing deployments?

**Decision**: Try `DefaultAzureCredential` first. If it raises (no identity
available), check for `DOCUMENT_INTELLIGENCE_KEY` as fallback. Log a WARNING
when falling back to API key. This way:
- **Production (Container Apps)**: Managed identity works immediately
- **Local dev with `az login`**: `DefaultAzureCredential` uses CLI credentials
- **Local dev without Azure**: Falls back to API key if set, or fails gracefully

**Rationale**: The current code checks for the key first, meaning a stale key
in env vars masks the working managed identity. Inverting means managed identity
always takes precedence unless truly unavailable.

**Implementation detail**: `DefaultAzureCredential()` does NOT raise on
construction — it raises on first use. So we construct the client with
`DefaultAzureCredential` and catch the `ClientAuthenticationError` during the
health check, falling back to API key only at that point. But for the
`_get_client()` function itself, we simply prefer credential-based construction
and only use key if explicitly requested by a new env var pattern.

Simpler approach chosen: Always use `DefaultAzureCredential` unless
`DOCUMENT_INTELLIGENCE_KEY` is set AND a new opt-in flag
`DOCUMENT_INTELLIGENCE_USE_KEY=true` is set. Actually — even simpler: just
invert the check. If credential auth is available (which it always is in
Container Apps), use it. Only fall back to key if credential is not available.
Since `DefaultAzureCredential()` never fails on construction, we can always
construct with it. The key fallback only applies if someone explicitly sets
`DOCUMENT_INTELLIGENCE_USE_KEY=true`.

**Final approach**: The simplest correct implementation:
1. Always construct with `DefaultAzureCredential` by default
2. Only use API key if `DOCUMENT_INTELLIGENCE_KEY` is set AND no managed identity
   is expected (i.e., env var `DOCUMENT_INTELLIGENCE_USE_KEY=true`)
3. Log WARNING when key auth is used

Actually — reviewing Robert's pattern and the codebase, the **simplest safe**
approach is:
1. If `DOCUMENT_INTELLIGENCE_KEY` is **not** set → use `DefaultAzureCredential`
   (unchanged behavior)
2. If `DOCUMENT_INTELLIGENCE_KEY` **is** set → still try `DefaultAzureCredential`
   first, fall back to key only if credential construction fails
3. Remove `DOCUMENT_INTELLIGENCE_KEY` from production env vars entirely

This means the code change is: **invert the if/else** and log a warning on the
key path. Production simply stops setting the key.

**Alternatives considered**:
- Feature flag approach — over-engineered for a simple priority swap
- Remove API key support entirely — breaks dev scenarios where someone uses a
  personal key without `az login`

### R4: Health Check Design for Worker Startup

**Question**: How should the worker test DI connectivity without slowing down
startup or blocking the poll loop?

**Decision**: Add a `_check_di_connectivity()` method called once during
`ConversionWorker.start()` before the poll loop. It calls
`_get_client().begin_analyze_document()` with a minimal synthetic PDF (or uses
a lighter API call). On success, log INFO with auth method detected. On failure,
log WARNING but don't crash — the worker should still process non-OCR jobs.

**Rationale**: A startup health check catches auth issues immediately (within
seconds of deploy) instead of waiting for the first scanned PDF upload, which
could be hours later. The check must be non-fatal because:
1. OCR is already non-fatal in the pipeline (Constitution Principle III)
2. The worker processes DOCX/PPTX files that don't need DI
3. DI might be temporarily unavailable

**Implementation approach**: Rather than calling the full `begin_analyze_document`
API (which costs money), we can simply instantiate the client and make a
lightweight call. The best option is to call `client.list_models()` or similar
lightweight endpoint. However, the azure-ai-documentintelligence SDK might not
expose a free health endpoint.

Simplest approach: construct the client, and verify the credential resolves
by catching `ClientAuthenticationError` during a lightweight operation. If we
use `DefaultAzureCredential`, we can call `credential.get_token()` directly
to verify the token can be obtained without making a DI API call.

**Final approach**: Call `DefaultAzureCredential().get_token("https://cognitiveservices.azure.com/.default")`
— this verifies the credential chain resolves without making any DI API call.
Zero cost, fast, and tells us exactly whether auth will work.

**Alternatives considered**:
- Call `begin_analyze_document` with a tiny PDF — costs money, slow
- Skip health check — status quo, auth failures are silent
- HTTP GET to DI endpoint — requires manual HTTP client, SDK doesn't expose it

### R5: Bicep Changes for RBAC and Env Var Cleanup

**Question**: How to assign Cognitive Services User role in Bicep and remove
the key from env vars?

**Decision**: 
1. Add a new Bicep module `infra/modules/cognitive-services-rbac.bicep` that
   assigns `Cognitive Services User` to the managed identity, scoped to the
   Document Intelligence resource
2. Add `AZURE_CLIENT_ID` to the shared env vars in `container-apps.bicep`
   (set to the managed identity's client ID)
3. Do NOT add `DOCUMENT_INTELLIGENCE_KEY` to Bicep — it was never there
   (it was set manually in production)
4. Add a shell script `scripts/assign-di-rbac.sh` for the manual RBAC
   assignment (same pattern as `scripts/assign-storage-rbac.sh`)

**Rationale**: The RBAC assignment may need to be done once by an admin with
Owner/User Access Administrator permissions, similar to the storage RBAC script.
A Bicep module is ideal for IaC but the deployment principal may not have
permissions to assign roles on the Cognitive Services resource.

**Alternatives considered**:
- Bicep-only — might fail if deployment SPN lacks role assignment permissions
- Manual-only — not repeatable, no IaC record
- Both — best of both worlds (chosen)

### R6: Backward Compatibility Analysis

**Question**: Can this change be deployed without coordination?

**Decision**: Yes. The deployment is backwards compatible:
1. **Before deploy**: Production has expired `DOCUMENT_INTELLIGENCE_KEY` set.
   Current code tries key → fails → OCR fails. (Current state: broken)
2. **After code deploy (before RBAC)**: New code tries `DefaultAzureCredential`
   → fails (no role assigned yet) → falls back to key → still fails. No change.
3. **After RBAC assignment**: New code tries `DefaultAzureCredential` → succeeds.
   Key fallback never reached. OCR works.
4. **After key removal**: Clean state. No stale secrets.

The deployment order is:
1. Deploy new code (safe — behavior unchanged until RBAC is assigned)
2. Assign RBAC role to managed identity
3. Remove `DOCUMENT_INTELLIGENCE_KEY` from production env vars
4. Verify OCR works

**Rationale**: This three-step rollout means each step is independently safe
and reversible. If RBAC assignment fails, the key path still works (or fails
the same way it does today). If the key is removed prematurely, re-adding it
is trivial.

### R7: Impact on Existing Tests

**Question**: Will the auth inversion break any existing tests?

**Decision**: No existing tests are affected. Analysis:
- `tests/unit/` — No tests reference `_get_client()`, `DocumentIntelligenceClient`,
  or `DOCUMENT_INTELLIGENCE_KEY`. The only OCR reference is in
  `tests/integration/test_html_wcag_compliance.py` which imports `OcrPageResult`
  data classes, not the client.
- `tests/unit/test_phase13_hardening.py` — Tests password protection and blob
  retry logic, not OCR auth.
- The `_get_client()` function is only called from `ocr_pdf_pages()`, which is
  imported lazily in `app/worker.py`.

**New tests needed**: Unit tests for the inverted `_get_client()` auth logic and
the DI health check.
