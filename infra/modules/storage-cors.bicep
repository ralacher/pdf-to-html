// ──────────────────────────────────────────────────────────────
// storage-cors.bicep — Blob Storage CORS rules
//
// Codifies the CORS configuration that was previously applied
// manually via `az storage cors add`. Without this, redeploying
// the storage account wipes CORS and breaks browser uploads.
//
// Required origins:
//   - Frontend Container App (production)
//   - localhost:3000 (local development)
// ──────────────────────────────────────────────────────────────

@description('Existing storage account name')
param storageAccountName string

@description('Frontend app URL including protocol (e.g. https://ca-pdftohtml-frontend.xxx.azurecontainerapps.io)')
param frontendUrl string

// ── Existing Storage Account ──────────────────────────────────
// Note: storage account must be in the same resource group as the
// deployment target for child-resource deployment to work.

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' existing = {
  name: storageAccountName
}

// ── Blob Service with CORS ────────────────────────────────────

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storageAccount
  name: 'default'
  properties: {
    cors: {
      corsRules: [
        {
          // Allow browser-based SAS uploads from the frontend and local dev
          allowedOrigins: [
            frontendUrl
            'http://localhost:3000'
          ]
          allowedMethods: [
            'PUT'
            'OPTIONS'
          ]
          allowedHeaders: [
            'x-ms-blob-type'
            'content-type'
            'x-ms-meta-*'
          ]
          exposedHeaders: []
          maxAgeInSeconds: 3600
        }
      ]
    }
  }
}

// ── Outputs ───────────────────────────────────────────────────

output corsConfigured bool = true
