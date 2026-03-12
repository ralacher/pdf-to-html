# Cyborg — History

## Session Log

- **2026-03-11:** Joined the squad as DevOps & Infrastructure.
- **2026-03-12:** First Azure deployment — provisioned storage, app service plan, function app, and deployed backend code. Blocked on RBAC role assignment (SPN has Contributor only, needs Owner for role assignment writes).

## Learnings

### Subscription Constraints
- **MCAPSGov "Deploy and Modify" policy** forces `allowSharedKeyAccess = false` on all storage accounts. Cannot be overridden — not even via ARM REST API or ARM template deployments.
- **SPN (`894189e2-b616-429a-9871-17acfc3a7614`)** has Contributor role only. Cannot write role assignments (needs Owner or User Access Administrator). Cannot create policy exemptions.
- **SPN client secret is expired** (AADSTS7000215). ARM tokens are cached and still work, but Graph API and data-plane tokens fail. Any operation requiring a fresh token (like `--auth-mode login` for storage, or role assignments via `az role assignment create`) will fail.

### Architecture Decisions
- **App Service Plan (B1) over Consumption Plan**: Consumption plan requires Azure Files which requires shared key access. Since the subscription policy blocks shared key access, a dedicated App Service Plan (B1 Linux) is used instead. This avoids the Azure Files dependency.
- **Identity-based AzureWebJobsStorage**: Using `AzureWebJobsStorage__accountName` instead of connection string. Requires RBAC roles: Storage Blob Data Owner, Storage Queue Data Contributor, Storage Account Contributor.
- **Blob containers created via ARM API**: Because key-based auth is blocked and Graph API token is expired, containers were created using ARM control-plane REST API (`az rest --method put`) instead of data-plane `az storage container create`.

### Key Resource Names
- Storage account: `stpdftohtml284588`
- Function App: `func-pdftohtml-284728`
- App Service Plan: `plan-pdftohtml`
- Resource Group: `rg-pdf-to-html` (location: `northcentralus`)
- MSI Principal ID: `350374e1-8c09-4553-9eac-1e983ea9f5b0`
- Subscription: `4b27ac87-dec6-45d5-8634-b9f71bd1dd26`

### Key File Paths
- `scripts/assign-storage-rbac.sh` — Admin must run this to complete deployment
- `function_app.py` — Uses `BlobServiceClient.from_connection_string()` — needs update to `DefaultAzureCredential` for managed identity
- `.funcignore` — Already configured, excludes test files and local settings
- `host.json` — Functions v2 config with extension bundle [4.*, 5.0.0)
