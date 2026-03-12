// ──────────────────────────────────────────────────────────────
// prod.bicepparam — Production environment parameters
// ──────────────────────────────────────────────────────────────
using '../main.bicep'

param environmentName = 'prod'
param location = 'eastus'

// ⚠️ KNOWN RISK: Dev and prod share the same storage account.
// Production data is NOT isolated from dev. A dev deployment that
// deletes containers or blobs will affect production.
// TODO: Provision a dedicated prod storage account (future sprint).
param storageAccountName = 'stpdftohtml331ef3'
param storageAccountResourceGroup = 'rg-pdftohtml'

// ACR name — must match ACR_NAME in .github/workflows/deploy-aca.yml
param acrName = 'crpdftohtml'

param documentIntelligenceEndpoint = ''
param imageTag = 'latest'
