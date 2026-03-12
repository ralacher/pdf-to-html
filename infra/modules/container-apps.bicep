// ──────────────────────────────────────────────────────────────
// container-apps.bicep — Container Apps Environment + 3 Apps
//
// 1. ca-pdftohtml-api      — FastAPI backend (port 8000)
// 2. ca-pdftohtml-worker   — Queue worker (same image, different cmd)
// 3. ca-pdftohtml-frontend — Next.js frontend (port 3000)
// ──────────────────────────────────────────────────────────────

@description('Azure region')
param location string = resourceGroup().location

@description('Container Apps Environment name')
param environmentName string

@description('Log Analytics workspace resource ID')
param logAnalyticsWorkspaceId string

@description('ACR login server (e.g. crpdftohtml.azurecr.io)')
param acrLoginServer string

@description('ACR resource name')
param acrName string

@description('Existing storage account name')
param storageAccountName string

@description('Resource group of the existing storage account')
param storageAccountResourceGroup string

@description('Azure Document Intelligence endpoint')
param documentIntelligenceEndpoint string = ''

@description('Container image tag')
param imageTag string = 'latest'

// ── Variables ─────────────────────────────────────────────────

var apiImageName = '${acrLoginServer}/pdf-to-html-api:${imageTag}'
var frontendImageName = '${acrLoginServer}/pdf-to-html-frontend:${imageTag}'

// ── Existing Storage Account ──────────────────────────────────

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' existing = {
  name: storageAccountName
  scope: resourceGroup(storageAccountResourceGroup)
}

// Build connection string from storage account keys
var storageConnectionString = 'DefaultEndpointsProtocol=https;AccountName=${storageAccountName};AccountKey=${storageAccount.listKeys().keys[0].value};EndpointSuffix=core.windows.net'

// ── Existing ACR (for role assignment) ────────────────────────

resource acr 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' existing = {
  name: acrName
}

// ── User-Assigned Managed Identity ────────────────────────────

resource managedIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-pdftohtml-apps'
  location: location
}

// AcrPull role assignment — let Container Apps pull images
var acrPullRoleId = '7f951dda-4ed3-4680-a7ca-43fe172d538d'  // AcrPull built-in role

resource acrPullAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, managedIdentity.id, acrPullRoleId)
  scope: acr
  properties: {
    principalId: managedIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPullRoleId)
  }
}

// ── Container Apps Environment ────────────────────────────────

resource containerAppsEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: environmentName
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: reference(logAnalyticsWorkspaceId, '2023-09-01').customerId
        sharedKey: listKeys(logAnalyticsWorkspaceId, '2023-09-01').primarySharedKey
      }
    }
    zoneRedundant: false
  }
}

// ── Shared environment variables ──────────────────────────────

var sharedEnvVars = [
  { name: 'AZURE_STORAGE_CONNECTION_STRING', value: storageConnectionString }
  { name: 'INPUT_CONTAINER', value: 'files' }
  { name: 'OUTPUT_CONTAINER', value: 'converted' }
  { name: 'QUEUE_NAME', value: 'conversion-jobs' }
  { name: 'LOG_LEVEL', value: 'INFO' }
  { name: 'DOCUMENT_INTELLIGENCE_ENDPOINT', value: documentIntelligenceEndpoint }
]

// ── 1. API Container App ──────────────────────────────────────

resource apiApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'ca-pdftohtml-api'
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${managedIdentity.id}': {}
    }
  }
  properties: {
    managedEnvironmentId: containerAppsEnv.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8000
        transport: 'http'
        corsPolicy: {
          allowedOrigins: ['*']
          allowedMethods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS']
          allowedHeaders: ['*']
        }
      }
      registries: [
        {
          server: acrLoginServer
          identity: managedIdentity.id
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'api'
          image: apiImageName
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: sharedEnvVars
          probes: [
            {
              type: 'Liveness'
              httpGet: {
                path: '/health'
                port: 8000
              }
              initialDelaySeconds: 10
              periodSeconds: 30
              failureThreshold: 3
            }
            {
              type: 'Readiness'
              httpGet: {
                path: '/ready'
                port: 8000
              }
              initialDelaySeconds: 5
              periodSeconds: 10
              failureThreshold: 3
            }
          ]
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 5
        rules: [
          {
            name: 'http-scale'
            http: {
              metadata: {
                concurrentRequests: '50'
              }
            }
          }
        ]
      }
    }
  }
  dependsOn: [acrPullAssignment]
}

// ── 2. Worker Container App ───────────────────────────────────

resource workerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'ca-pdftohtml-worker'
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${managedIdentity.id}': {}
    }
  }
  properties: {
    managedEnvironmentId: containerAppsEnv.id
    configuration: {
      activeRevisionsMode: 'Single'
      registries: [
        {
          server: acrLoginServer
          identity: managedIdentity.id
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'worker'
          image: apiImageName
          command: ['python', '-m', 'app.worker']
          resources: {
            cpu: json('1.0')
            memory: '2Gi'
          }
          env: concat(sharedEnvVars, [
            { name: 'WORKER_MODE', value: 'true' }
          ])
        }
      ]
      scale: {
        minReplicas: 0
        maxReplicas: 10
        rules: [
          {
            name: 'queue-scale'
            azureQueue: {
              queueName: 'conversion-jobs'
              queueLength: 1
              auth: [
                {
                  secretRef: 'storage-connection'
                  triggerParameter: 'connection'
                }
              ]
            }
          }
        ]
      }
    }
  }
  dependsOn: [acrPullAssignment]
}

// ── 3. Frontend Container App ─────────────────────────────────

resource frontendApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'ca-pdftohtml-frontend'
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${managedIdentity.id}': {}
    }
  }
  properties: {
    managedEnvironmentId: containerAppsEnv.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 3000
        transport: 'http'
      }
      registries: [
        {
          server: acrLoginServer
          identity: managedIdentity.id
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'frontend'
          image: frontendImageName
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
          env: [
            { name: 'NODE_ENV', value: 'production' }
            { name: 'NEXT_PUBLIC_API_URL', value: 'https://${apiApp.properties.configuration.ingress.fqdn}' }
            // BACKEND_URL is baked into Next.js rewrites at build time via --build-arg in
            // deploy-aca.yml. We also set it here so Bicep deployments don't wipe the value
            // and for documentation/consistency with the deploy workflow.
            { name: 'BACKEND_URL', value: 'https://${apiApp.properties.configuration.ingress.fqdn}' }
          ]
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 3
        rules: [
          {
            name: 'http-scale'
            http: {
              metadata: {
                concurrentRequests: '100'
              }
            }
          }
        ]
      }
    }
  }
  dependsOn: [acrPullAssignment]
}

// ── Outputs ───────────────────────────────────────────────────

output apiFqdn string = 'https://${apiApp.properties.configuration.ingress.fqdn}'
output frontendFqdn string = 'https://${frontendApp.properties.configuration.ingress.fqdn}'
output workerName string = workerApp.name
output environmentId string = containerAppsEnv.id
