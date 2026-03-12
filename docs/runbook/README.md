# NCDIT Operations Runbook

This directory contains the encrypted operations runbook for the pdf-to-html converter project.

## Architecture

- **Source:** `docs/runbook/index.html` contains the raw runbook HTML
- **Encryption:** StaticCrypt v3 encrypts the runbook before deployment
- **Deployment:** GitHub Actions deploys to GitHub Pages
- **Live URL:** [ralacher.github.io/pdf-to-html/runbook/](https://ralacher.github.io/pdf-to-html/runbook/)

## How It Works

1. The raw runbook lives in `docs/runbook/index.html` (unencrypted)
2. When changes are pushed to `001-sean` or `main` branches, the `deploy-runbook.yml` workflow triggers
3. The workflow uses StaticCrypt to password-protect the HTML
4. The encrypted version is deployed to GitHub Pages at `/runbook/`

## Deployment

### Automatic Deployment

The workflow automatically deploys when:
- Changes are pushed to `docs/runbook/**` on the `001-sean` or `main` branch

### Manual Deployment

To manually trigger deployment:
1. Go to Actions → "Deploy Runbook to GitHub Pages"
2. Click "Run workflow"
3. Select the branch and click "Run workflow"

## Setting the Password

The runbook password is stored as a GitHub Actions secret:

1. Go to repository Settings → Secrets and variables → Actions
2. Create a secret named `RUNBOOK_PASSWORD`
3. Set the password value (share this with authorized team members via secure channel)

**Important:** The password is only used during deployment. Users accessing the runbook will need to enter this password to decrypt and view the content.

## StaticCrypt Configuration

The workflow uses StaticCrypt v3 with NCDIT branding:

- **Title:** "NCDIT Operations Runbook"
- **Primary Color:** Navy (`#003366`)
- **Secondary Color:** Dark navy (`#0a1628`)
- **Instructions:** "Enter the runbook password to access operations documentation."

## Security Notes

- The raw `index.html` is committed to the repository (team members with repo access can view it)
- The deployed version is password-protected and publicly accessible at the GitHub Pages URL
- StaticCrypt uses in-browser decryption (no server-side secrets)
- To change the password, update the `RUNBOOK_PASSWORD` secret and re-deploy

## Local Testing

To test the encrypted version locally:

```bash
# Install staticrypt
npm install -g staticrypt

# Encrypt the runbook
staticrypt docs/runbook/index.html -p "test-password" \
  -o docs/runbook/encrypted.html \
  --short \
  --template-title "NCDIT Operations Runbook" \
  --template-instructions "Enter the runbook password to access operations documentation." \
  --template-color-primary "#003366" \
  --template-color-secondary "#0a1628"

# Open encrypted.html in a browser and test with "test-password"
```

## Troubleshooting

### Workflow fails with "RUNBOOK_PASSWORD not set"
- Ensure the secret exists in repository settings
- Check that the secret name matches exactly (case-sensitive)

### Deployed page shows 404
- Verify GitHub Pages is enabled (Settings → Pages)
- Check that Pages is configured to deploy from GitHub Actions
- Wait 2-3 minutes after deployment for Pages to update

### Password prompt doesn't appear
- Check browser console for JavaScript errors
- Verify the encrypted file was generated correctly
- Try clearing browser cache and reloading

## Maintenance

- **Update runbook content:** Edit `docs/runbook/index.html` directly
- **Change password:** Update the `RUNBOOK_PASSWORD` secret and re-run the workflow
- **Update styling:** Modify the StaticCrypt template flags in `.github/workflows/deploy-runbook.yml`
