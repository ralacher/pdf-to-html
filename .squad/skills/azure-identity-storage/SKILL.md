---
name: "azure-identity-storage"
description: "Deploying Azure Functions with identity-based storage when key access is blocked by policy"
domain: "infrastructure, azure, devops"
confidence: "high"
source: "earned: first deployment of pdf-to-html to MCAPS-governed subscription"
---

## Context
When deploying to Azure subscriptions governed by MCAPSGov policies, storage accounts are forced to have `allowSharedKeyAccess = false`. This breaks the default Azure Functions setup which relies on connection strings with account keys.

## Patterns

### Use ARM API for container creation
When key-based auth is blocked and the SPN token can't authenticate to the data plane, use ARM control-plane API:
```bash
az rest --method put \
  --url "https://management.azure.com{storage_resource_id}/blobServices/default/containers/{name}?api-version=2023-05-01" \
  --body '{"properties": {"publicAccess": "None"}}'
```

### Use App Service Plan instead of Consumption
Consumption Plan on Linux requires Azure Files → requires shared key access. Use a B1 App Service Plan to avoid this dependency.

### Identity-based AzureWebJobsStorage
Set `AzureWebJobsStorage__accountName` instead of a connection string. Requires RBAC roles on the MSI:
- Storage Blob Data Owner
- Storage Queue Data Contributor
- Storage Account Contributor

### Application code must use DefaultAzureCredential
Replace `BlobServiceClient.from_connection_string()` with:
```python
from azure.identity import DefaultAzureCredential
credential = DefaultAzureCredential()
client = BlobServiceClient(account_url=f"https://{account_name}.blob.core.windows.net", credential=credential)
```

## Anti-Patterns
- **Don't rely on `--allow-shared-key-access true`** — MCAPSGov Modify policy overrides it silently.
- **Don't use `az storage container create` with `--connection-string` or `--account-key`** — data plane calls will be rejected.
- **Don't assume Contributor role can assign RBAC** — it cannot. Escalate to Owner/UAA.
