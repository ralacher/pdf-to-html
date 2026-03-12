#!/usr/bin/env bash
# assign-storage-rbac.sh
# -----------------------------------------------------------------------
# Assigns required RBAC roles to the Function App's managed identity
# so it can access the storage account via identity-based auth.
#
# REQUIRES: Owner or User Access Administrator role on the storage account.
# The Contributor SPN cannot run this — an admin must execute it.
# -----------------------------------------------------------------------

set -euo pipefail

MSI_PRINCIPAL="350374e1-8c09-4553-9eac-1e983ea9f5b0"
STORAGE_SCOPE="/subscriptions/4b27ac87-dec6-45d5-8634-b9f71bd1dd26/resourceGroups/rg-pdf-to-html/providers/Microsoft.Storage/storageAccounts/stpdftohtml284588"

echo "Assigning RBAC roles to Function App MSI ($MSI_PRINCIPAL)..."

# Storage Blob Data Owner — read/write/delete blobs, manage containers
az role assignment create \
  --assignee-object-id "$MSI_PRINCIPAL" \
  --assignee-principal-type ServicePrincipal \
  --role "Storage Blob Data Owner" \
  --scope "$STORAGE_SCOPE"

# Storage Queue Data Contributor — Azure Functions uses queues internally
az role assignment create \
  --assignee-object-id "$MSI_PRINCIPAL" \
  --assignee-principal-type ServicePrincipal \
  --role "Storage Queue Data Contributor" \
  --scope "$STORAGE_SCOPE"

# Storage Account Contributor — manage storage account settings
az role assignment create \
  --assignee-object-id "$MSI_PRINCIPAL" \
  --assignee-principal-type ServicePrincipal \
  --role "Storage Account Contributor" \
  --scope "$STORAGE_SCOPE"

echo ""
echo "Done. Restart the function app to apply:"
echo "  az functionapp restart --name func-pdftohtml-284728 --resource-group rg-pdf-to-html"
