// ──────────────────────────────────────────────────────────────
// main.bicep — Orchestrator for pdf-to-html Azure Container Apps
//
// Deploys: ACR, Container Apps Environment, 3 Container Apps,
// Event Grid system topic + subscription.
//
// Usage:
//   az deployment group create \
//     --resource-group rg-pdftohtml \
//     --template-file infra/main.bicep \
//     --parameters infra/parameters/dev.bicepparam
// ──────────────────────────────────────────────────────────────

targetScope = 'resourceGroup'

// ── Parameters ────────────────────────────────────────────────

@description('Azure region for all resources')
param location string = resourceGroup().location

@description('Environment name used for resource naming (dev, staging, prod)')
@allowed(['dev', 'staging', 'prod'])
param environmentName string

@description('Name of the existing storage account')
param storageAccountName string

@description('Resource group containing the existing storage account')
param storageAccountResourceGroup string = resourceGroup().name

@description('Azure Document Intelligence endpoint URL')
param documentIntelligenceEndpoint string = ''

@description('Container image tag (defaults to latest)')
param imageTag string = 'latest'

@description('Azure Container Registry name (must match ACR_NAME in deploy-aca.yml)')
param acrName string = 'crpdftohtml'

// ── Variables ─────────────────────────────────────────────────

var containerAppsEnvName = 'cae-pdftohtml-${environmentName}'
var logAnalyticsName = 'log-pdftohtml-${environmentName}'

// ── Existing Storage Account Reference ────────────────────────

resource existingStorage 'Microsoft.Storage/storageAccounts@2023-05-01' existing = {
  name: storageAccountName
  scope: resourceGroup(storageAccountResourceGroup)
}

// ── Log Analytics Workspace ───────────────────────────────────

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: logAnalyticsName
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

// ── Modules ───────────────────────────────────────────────────

module acr 'modules/container-registry.bicep' = {
  name: 'acr-deployment'
  params: {
    name: acrName
    location: location
  }
}

module containerApps 'modules/container-apps.bicep' = {
  name: 'container-apps-deployment'
  params: {
    location: location
    environmentName: containerAppsEnvName
    logAnalyticsWorkspaceId: logAnalytics.id
    acrLoginServer: acr.outputs.loginServer
    acrName: acr.outputs.name
    storageAccountName: storageAccountName
    storageAccountResourceGroup: storageAccountResourceGroup
    documentIntelligenceEndpoint: documentIntelligenceEndpoint
    imageTag: imageTag
  }
}

module eventGrid 'modules/event-grid.bicep' = {
  name: 'event-grid-deployment'
  params: {
    location: location
    storageAccountName: storageAccountName
    storageAccountResourceGroup: storageAccountResourceGroup
  }
}

module storageCors 'modules/storage-cors.bicep' = {
  name: 'storage-cors-deployment'
  params: {
    storageAccountName: storageAccountName
    frontendUrl: containerApps.outputs.frontendFqdn
  }
}

// ── Outputs ───────────────────────────────────────────────────

output acrLoginServer string = acr.outputs.loginServer
output apiUrl string = containerApps.outputs.apiFqdn
output frontendUrl string = containerApps.outputs.frontendFqdn
output workerName string = containerApps.outputs.workerName
