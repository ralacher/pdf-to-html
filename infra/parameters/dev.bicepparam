// ──────────────────────────────────────────────────────────────
// dev.bicepparam — Development environment parameters
// ──────────────────────────────────────────────────────────────
using '../main.bicep'

param environmentName = 'dev'
param location = 'eastus'

// ⚠️ KNOWN RISK: Dev and prod share the same storage account.
// Dev testing could corrupt or delete production blobs.
// TODO: Create a separate storage account for dev (future sprint).
// See: https://github.com/NCDIT-DIS/pdf-to-html/issues — track as backlog item.
param storageAccountName = 'stpdftohtml331ef3'
param storageAccountResourceGroup = 'rg-pdftohtml'

// ACR name — must match ACR_NAME in .github/workflows/deploy-aca.yml
param acrName = 'crpdftohtml'

param documentIntelligenceEndpoint = ''
param imageTag = 'latest'
