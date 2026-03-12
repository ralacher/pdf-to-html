# Decision: Azure Deployment Architecture

**Author:** Cyborg (DevOps & Infrastructure)  
**Date:** 2026-03-12  
**Status:** Partially Implemented (blocked on RBAC)

## Context

First deployment of the pdf-to-html backend to Azure. The subscription has strict governance policies (MCAPSGov) that enforce identity-based storage authentication.

## Decisions Made

### App Service Plan (B1) instead of Consumption Plan
- **Decision:** Use a dedicated B1 Linux App Service Plan for the Function App.
- **Rationale:** The subscription policy forces `allowSharedKeyAccess = false` on all storage accounts. Azure Functions Consumption Plan on Linux requires Azure Files, which requires shared key access. A dedicated plan avoids this dependency entirely.
- **Trade-off:** Higher baseline cost (~$13/month for B1 vs. pay-per-execution for Consumption). Acceptable for initial deployment; can revisit if RBAC/policy constraints are resolved.

### Identity-based AzureWebJobsStorage
- **Decision:** Use `AzureWebJobsStorage__accountName` instead of the traditional connection string.
- **Rationale:** Key-based auth is blocked by subscription policy. Identity-based storage is the only option available.
- **Requires:** RBAC roles (Storage Blob Data Owner, Storage Queue Data Contributor, Storage Account Contributor) assigned to the Function App's system-assigned managed identity.

### Application Code Needs Managed Identity Support
- **Decision:** `function_app.py` currently uses `BlobServiceClient.from_connection_string()`. This must be updated to use `DefaultAzureCredential` from `azure-identity`.
- **Impact:** Wonder-Woman needs to update `function_app.py` to detect whether `AzureWebJobsStorage` is a connection string or an account name, and use the appropriate authentication method.

## Blocking Issue

The deployment SPN has Contributor role only. It cannot:
1. Assign RBAC roles (`Microsoft.Authorization/roleAssignments/write`)
2. Create policy exemptions (`Microsoft.Authorization/policyExemptions/write`)

**Action Required:** An admin with Owner role must run `scripts/assign-storage-rbac.sh` to assign the required RBAC roles to the Function App's managed identity.

## Impact on Other Agents

- **Wonder-Woman:** Must update `function_app.py` to support `DefaultAzureCredential` for blob access (not just connection string).
- **Flash:** No frontend changes needed. Backend URL is `https://func-pdftohtml-284728.azurewebsites.net`.
- **Aquaman:** Integration tests should support both connection string and managed identity auth modes.
- **Batman:** Review the B1 plan decision and managed identity architecture.
