# Runbook Encryption Guide

The `index.html` runbook is designed to be encrypted with **StaticCrypt** before deployment.

## Prerequisites

Install StaticCrypt globally:
```bash
npm install -g staticrypt
```

## Encrypt the Runbook

```bash
cd /workspaces/pdf-to-html/docs/runbook

# Encrypt with a strong password
staticrypt index.html -p "YOUR_STRONG_PASSWORD_HERE"

# This generates:
# - index.html (encrypted version, overwrites original)
# - index_encrypted.html (backup, if --no-remember flag used)
```

## Recommended StaticCrypt Options

For production, use these flags:

```bash
staticrypt index.html \
  --password "YOUR_STRONG_PASSWORD" \
  --title "NCDIT WCAG Converter — Runbook (Protected)" \
  --instructions "This runbook is for authorized NCDIT personnel only. Enter the password to access." \
  --remember 30 \
  --template-color-primary "#003366" \
  --template-color-secondary "#38bdf8"
```

**Options explained:**
- `--title`: Sets the page title shown before unlock
- `--instructions`: Custom message on the password prompt
- `--remember 30`: Remembers password for 30 days (stores encrypted token in localStorage)
- `--template-color-primary`: NCDIT brand navy (#003366)
- `--template-color-secondary`: Sky blue accent (#38bdf8)

## Decrypt for Updates

To update the runbook:

1. Keep a backup of the **original unencrypted** `index.html` in version control
2. Make edits to the unencrypted version
3. Re-encrypt after changes

**DO NOT** commit the encrypted version to Git. Only commit the source (unencrypted) HTML.

## Deployment

Deploy the **encrypted** `index.html` to:
- Azure Static Web Apps
- Azure Blob Storage (static website hosting)
- Any static file hosting service

The encrypted file is self-contained — no external dependencies except the Google Fonts CDN.

## Password Management

- **Password Complexity:** Minimum 16 characters, mixed case, numbers, symbols
- **Rotation:** Change password quarterly
- **Distribution:** Share via secure channel (1Password, LastPass, Azure Key Vault)
- **Access Control:** Only provide to on-call engineers and DevOps team

## Security Notes

- StaticCrypt uses **AES-256-GCM** encryption
- Password is never sent to the server — all decryption happens client-side
- The encrypted HTML includes the crypto libraries inline (no CDN dependencies)
- Brute-force protection: Password hashing uses 100,000+ iterations

## Example Workflow

```bash
# 1. Edit the source
vim index.html

# 2. Encrypt for deployment
staticrypt index.html -p "$(cat /path/to/secure/password.txt)"

# 3. Deploy the encrypted version
az storage blob upload \
  --account-name ncditwcagstorage \
  --container-name '$web' \
  --name runbook/index.html \
  --file index.html \
  --content-type text/html
```

---

**Built for NCDIT by Flash (Frontend Developer)**
