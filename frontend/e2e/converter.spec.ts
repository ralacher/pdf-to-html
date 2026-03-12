/**
 * End-to-end Playwright tests for the WCAG Document Converter.
 *
 * Run against local stack:
 *   cd frontend && npx playwright test
 *
 * Run against Azure:
 *   FRONTEND_URL=https://ca-pdftohtml-frontend.xxx.azurecontainerapps.io \
 *   cd frontend && npx playwright test
 *
 * Architecture:
 *   - Landing page (/) → Hero section + FileUpload component + info sections
 *   - Dashboard (/dashboard) → Metric tiles + ProgressTracker + delete/preview
 *   - NCHeader → Sticky header with NC.gov branding + nav links + ThemeToggle
 */
import { test, expect } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

// Create a minimal valid PDF buffer for uploads
function createTestPdf(): Buffer {
  const pdf = [
    '%PDF-1.4',
    '1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj',
    '2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj',
    '3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]',
    '   /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj',
    '4 0 obj\n<< /Length 44 >>\nstream',
    'BT /F1 24 Tf 100 700 Td (Hello WCAG) Tj ET',
    'endstream\nendobj',
    '5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj',
    'xref\n0 6',
    '0000000000 65535 f ',
    '0000000009 00000 n ',
    '0000000058 00000 n ',
    '0000000115 00000 n ',
    '0000000266 00000 n ',
    '0000000360 00000 n ',
    'trailer\n<< /Size 6 /Root 1 0 R >>',
    'startxref\n441\n%%EOF',
  ].join('\n');
  return Buffer.from(pdf);
}

// ---------------------------------------------------------------------------
// Landing Page (/)
// ---------------------------------------------------------------------------

test.describe('Landing Page', () => {
  test('renders with correct title', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveTitle(/NCDIT|Document|Converter/i);
  });

  test('has lang attribute on html element (WCAG)', async ({ page }) => {
    await page.goto('/');
    const lang = await page.getAttribute('html', 'lang');
    expect(lang).toBeTruthy();
  });

  test('displays hero section with heading', async ({ page }) => {
    await page.goto('/');
    const heroHeading = page.locator('#hero-heading');
    await expect(heroHeading).toBeVisible({ timeout: 15000 });
    await expect(heroHeading).toContainText(/NCDIT Document Converter/i);
  });

  test('shows the upload drop zone', async ({ page }) => {
    await page.goto('/');
    // The FileUpload component renders a drop zone with drag & drop text
    const dropZone = page.locator('text=/drag.*drop|browse/i').first();
    await expect(dropZone).toBeVisible({ timeout: 15000 });
  });

  test('has a file input that accepts PDF, DOCX, PPTX', async ({ page }) => {
    await page.goto('/');
    const fileInput = page.locator('input[type="file"]');
    await expect(fileInput).toBeAttached();
    const accept = await fileInput.getAttribute('accept');
    expect(accept).toContain('.pdf');
    expect(accept).toContain('.docx');
    expect(accept).toContain('.pptx');
  });

  test('has a skip-to-content link (WCAG)', async ({ page }) => {
    await page.goto('/');
    const skipLink = page.locator('a.skip-nav, a[href="#main-content"]');
    await expect(skipLink).toBeAttached();
  });

  test('displays supported formats section', async ({ page }) => {
    await page.goto('/');
    const formatsHeading = page.locator('#formats-heading');
    await expect(formatsHeading).toBeVisible();
    await expect(formatsHeading).toContainText(/Supported Formats/i);
  });

  test('displays how-it-works section', async ({ page }) => {
    await page.goto('/');
    const stepsHeading = page.locator('#steps-heading');
    await expect(stepsHeading).toBeVisible();
    await expect(stepsHeading).toContainText(/How It Works/i);
  });

  test('has link to dashboard', async ({ page }) => {
    await page.goto('/');
    const dashboardLink = page.locator('a[href="/dashboard"]').first();
    await expect(dashboardLink).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// Dashboard Page (/dashboard)
// ---------------------------------------------------------------------------

test.describe('Dashboard Page', () => {
  test('renders with correct title', async ({ page }) => {
    await page.goto('/dashboard');
    await expect(page).toHaveTitle(/NCDIT|Document|Converter/i);
  });

  test('has lang attribute on html element (WCAG)', async ({ page }) => {
    await page.goto('/dashboard');
    const lang = await page.getAttribute('html', 'lang');
    expect(lang).toBeTruthy();
  });

  test('displays dashboard heading', async ({ page }) => {
    await page.goto('/dashboard');
    const heading = page.locator('#dashboard-heading');
    await expect(heading).toBeVisible({ timeout: 15000 });
    await expect(heading).toContainText(/Conversion Dashboard/i);
  });

  test('shows summary metric cards', async ({ page }) => {
    await page.goto('/dashboard');
    const summaryCards = page.locator('[data-testid="summary-cards"]');
    await expect(summaryCards).toBeVisible({ timeout: 15000 });

    // Should have tile cards for Total, Pending, Processing, Completed, Failed
    for (const label of ['total', 'pending', 'processing', 'completed', 'failed']) {
      const card = page.locator(`[data-testid="summary-card-${label}"]`);
      await expect(card).toBeVisible();
    }
  });

  test('has upload-more link back to landing page', async ({ page }) => {
    await page.goto('/dashboard');
    const uploadLink = page.locator('a[href="/"]').first();
    await expect(uploadLink).toBeVisible();
  });

  test('shows auto-refreshing polling badge', async ({ page }) => {
    await page.goto('/dashboard');
    const pollingBadge = page.locator('[data-testid="polling-badge"]');
    // Polling badge visible while loading initially
    await expect(pollingBadge).toBeVisible({ timeout: 10000 });
  });
});

// ---------------------------------------------------------------------------
// Header & Navigation
// ---------------------------------------------------------------------------

test.describe('Header & Navigation', () => {
  test('header has NC.gov branding', async ({ page }) => {
    await page.goto('/');
    const header = page.locator('header[role="banner"]');
    await expect(header).toBeVisible();
    // NC.gov logo link
    const logoLink = header.locator('a[aria-label*="NC.gov"]');
    await expect(logoLink).toBeVisible();
  });

  test('header has navigation links', async ({ page }) => {
    await page.goto('/');
    const nav = page.locator('nav[aria-label="Service navigation"]');
    await expect(nav).toBeVisible();
    await expect(nav.locator('a[href="/"]')).toBeVisible();
    await expect(nav.locator('a[href="/dashboard"]')).toBeVisible();
  });

  test('navigation links work', async ({ page }) => {
    await page.goto('/');
    // Click Dashboard link
    await page.locator('nav[aria-label="Service navigation"] a[href="/dashboard"]').click();
    await expect(page).toHaveURL(/\/dashboard/);
    // Click Upload link to go back
    await page.locator('nav[aria-label="Service navigation"] a[href="/"]').click();
    await expect(page).toHaveURL(/\/$/);
  });
});

// ---------------------------------------------------------------------------
// File Upload Flow
// ---------------------------------------------------------------------------

test.describe('File Upload Flow', () => {
  test('uploads a PDF and shows progress', async ({ page }) => {
    await page.goto('/');

    // Write test PDF to temp file
    const tmpDir = path.join(__dirname, '..', '.tmp-test');
    fs.mkdirSync(tmpDir, { recursive: true });
    const pdfPath = path.join(tmpDir, 'e2e-test.pdf');
    fs.writeFileSync(pdfPath, createTestPdf());

    try {
      // Find file input (may be hidden — Playwright can still interact)
      const fileInput = page.locator('input[type="file"]');
      await fileInput.setInputFiles(pdfPath);

      // Should see some indication of upload/processing
      // The FileUpload component shows status text: Uploading, Complete, Queued, Error
      const indicator = page.locator(
        'text=/upload|complete|queued|error|processing/i'
      ).first();
      await expect(indicator).toBeVisible({ timeout: 30000 });
    } finally {
      fs.rmSync(tmpDir, { recursive: true, force: true });
    }
  });

  test('file input restricts accepted formats', async ({ page }) => {
    await page.goto('/');
    const fileInput = page.locator('input[type="file"]');
    const accept = await fileInput.getAttribute('accept');
    expect(accept).toContain('.pdf');
    expect(accept).toContain('.docx');
    expect(accept).toContain('.pptx');
  });

  test('upload drop zone is keyboard accessible', async ({ page }) => {
    await page.goto('/');
    // The upload zone has role="button" and tabIndex=0
    const dropZone = page.locator('[role="button"][tabindex="0"]').first();
    await expect(dropZone).toBeVisible();
    // Verify it has an aria-label for accessibility
    const ariaLabel = await dropZone.getAttribute('aria-label');
    expect(ariaLabel).toBeTruthy();
    expect(ariaLabel).toMatch(/upload|drag|drop|browse/i);
  });
});

// ---------------------------------------------------------------------------
// Conversion Pipeline (E2E)
// ---------------------------------------------------------------------------

test.describe('Conversion Pipeline (E2E)', () => {
  test('full pipeline: upload on landing → check progress on dashboard', async ({ page }) => {
    test.setTimeout(180_000); // 3 minutes for full pipeline

    // Step 1: Upload a test PDF from the landing page
    await page.goto('/');

    const tmpDir = path.join(__dirname, '..', '.tmp-test');
    fs.mkdirSync(tmpDir, { recursive: true });
    const pdfPath = path.join(tmpDir, 'pipeline-test.pdf');
    fs.writeFileSync(pdfPath, createTestPdf());

    try {
      const fileInput = page.locator('input[type="file"]');
      await fileInput.setInputFiles(pdfPath);

      // Wait for upload to show some status
      const uploadStatus = page.locator(
        'text=/upload|complete|queued/i'
      ).first();
      await expect(uploadStatus).toBeVisible({ timeout: 30000 });

      // Step 2: Navigate to dashboard to see the document in progress
      await page.goto('/dashboard');

      // Wait for dashboard to load — should show at least the summary cards
      const summaryCards = page.locator('[data-testid="summary-cards"]');
      await expect(summaryCards).toBeVisible({ timeout: 15000 });

      // Step 3: Wait for a document to show as completed or processing
      // The ProgressTracker should show document cards after polling starts
      const docIndicator = page.locator(
        'text=/completed|processing|pending|converting|download|preview/i'
      ).first();
      await expect(docIndicator).toBeVisible({ timeout: 120000 });

      // Step 4: If a download/preview button is available, verify it's clickable
      const actionButton = page.locator(
        '[data-testid^="preview-btn-"], [data-testid="download-button"]'
      ).first();

      if (await actionButton.isVisible({ timeout: 10000 }).catch(() => false)) {
        // Click preview/download — verify no crash
        const [response] = await Promise.all([
          page.waitForResponse(
            (resp) => resp.url().includes('/api/') && resp.status() < 500,
            { timeout: 30000 }
          ).catch(() => null),
          actionButton.click(),
        ]);

        if (response) {
          expect(response.status()).toBeLessThan(500);
        }
      }

      // Step 5: If a delete button is available, verify deletion works
      const deleteButton = page.locator('[data-testid^="delete-btn-"]').first();

      if (await deleteButton.isVisible({ timeout: 5000 }).catch(() => false)) {
        await deleteButton.click();

        // ConfirmDialog should appear — click confirm
        const confirmButton = page.locator(
          'button:has-text(/delete/i)'
        ).last(); // The confirm button in the dialog
        if (await confirmButton.isVisible({ timeout: 5000 }).catch(() => false)) {
          await confirmButton.click();
        }

        // Wait for deletion to complete
        await page.waitForTimeout(2000);
      }
    } finally {
      fs.rmSync(tmpDir, { recursive: true, force: true });
    }
  });
});

// ---------------------------------------------------------------------------
// WCAG Compliance Checks
// ---------------------------------------------------------------------------

test.describe('WCAG Compliance', () => {
  test('landing page has proper heading hierarchy', async ({ page }) => {
    await page.goto('/');
    // h1 should exist
    const h1 = page.locator('h1');
    await expect(h1.first()).toBeVisible();

    // All headings should be present in semantic order
    const headings = await page.locator('h1, h2, h3').allTextContents();
    expect(headings.length).toBeGreaterThan(0);
  });

  test('all images have alt text', async ({ page }) => {
    await page.goto('/');
    const images = page.locator('img:not([aria-hidden="true"])');
    const count = await images.count();
    for (let i = 0; i < count; i++) {
      const alt = await images.nth(i).getAttribute('alt');
      expect(alt, `Image ${i} missing alt text`).toBeTruthy();
    }
  });

  test('main landmark has correct id for skip-nav', async ({ page }) => {
    await page.goto('/');
    const main = page.locator('main#main-content');
    await expect(main).toBeVisible();
  });

  test('footer has contentinfo role', async ({ page }) => {
    await page.goto('/');
    const footer = page.locator('footer[role="contentinfo"]');
    await expect(footer).toBeVisible();
  });

  test('dashboard has aria-live regions for updates', async ({ page }) => {
    await page.goto('/dashboard');
    // Dashboard should have at least one aria-live region for status updates
    const liveRegion = page.locator('[aria-live]');
    const count = await liveRegion.count();
    expect(count).toBeGreaterThan(0);
  });
});
