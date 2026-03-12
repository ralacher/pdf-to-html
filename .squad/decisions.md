# Squad Decisions

## Active Decisions

### 1. Frontend Architecture — Phase 1+2 Scaffold

**Author:** Flash (Frontend Developer)  
**Date:** 2026-03-11  
**Status:** Implemented

#### Context
Stood up the full Next.js 14 frontend from scratch, including design system tokens, layout shell, government branding components, and backend service layers.

#### Decisions Made

**Styled JSX for component-scoped CSS**
- Chose: Next.js built-in `<style jsx>` for GovBanner, NCHeader, NCFooter
- Over: CSS Modules or Tailwind
- Why: Zero config, co-located with components, no extra dependencies, works with SSR. Bootstrap handles layout; styled-jsx handles component-specific overrides.

**CSS Custom Properties for Design Tokens**
- Chose: CSS `--nc-*` custom properties in `digital-commons.css`
- Over: Sass variables, JS theme objects, or Tailwind config
- Why: Works natively in CSS, no build tooling required, easily consumed by both Bootstrap overrides and component styles. Future theme switching (dark mode, high-contrast) becomes trivial.

**XMLHttpRequest for Upload Progress**
- Chose: XHR in `uploadService.ts`
- Over: Fetch API or third-party upload libraries (tus, Uppy)
- Why: Fetch API doesn't support `upload.onprogress`. XHR is the only browser-native option for real-time upload progress bars. Keeps dependencies minimal.

**Polling-based Status Updates**
- Chose: `setTimeout`-based polling in `statusService.ts` (3s interval)
- Over: WebSocket, SSE, or long-polling
- Why: Simpler backend contract (stateless HTTP), works with Azure Functions consumption plan, easy to implement. Can migrate to SSE later if needed. Minimum 1s guard prevents accidental server overload.

#### Impact
- Wonder-Woman: Backend API must implement `POST /api/upload` (returns SAS token) and `GET /api/status` / `GET /api/status/:id` endpoints.
- Cyborg: No WebSocket infrastructure needed initially; standard HTTP endpoints suffice.
- Aquaman: axe-core is installed and ready for dev-time accessibility auditing.

---

### 2. Phase 2 Backend Architecture

**Author:** Wonder-Woman (Backend Developer)  
**Date:** 2026-03-11  
**Status:** Implemented

#### Context
Phase 2 required three new HTTP API endpoints (SAS upload, status query, download URLs) plus shared infrastructure modules (models, status tracking, WCAG validation).

#### Decisions Made

**Blob metadata for status tracking (no database)**
- Decision: Store all document status as Azure Blob metadata on the uploaded file in the `files/` container.
- Rationale: Avoids provisioning a database service for what is currently a small-scale deployment. Blob metadata is transactional, free, and co-located with the files. If scale requires it later, the `status_service.py` interface can be swapped to CosmosDB without changing callers.
- Trade-off: `list_documents()` does a full container scan. Acceptable for < 1,000 documents; will need pagination or an index beyond that.

**SAS token upload flow with placeholder blob**
- Decision: `generate_sas_token` creates an empty placeholder blob with full metadata before returning the SAS URL to the browser.
- Rationale: This ensures the status service can track the document immediately (e.g., the frontend can poll `/documents/status` right away). The browser's PUT upload overwrites the blob content but preserves metadata.

**Python-side WCAG pre-validation**
- Decision: `wcag_validator.py` implements 7 WCAG rules in pure Python using regex parsing. This is a server-side pre-check, not a replacement for axe-core.
- Rationale: Catches critical issues (missing alt text, broken heading hierarchy, missing table headers) before the HTML even reaches the browser. Reduces round-trips for obvious violations. The frontend still runs full axe-core for comprehensive validation.

**models.py re-exports existing dataclasses**
- Decision: `models.py` imports `TextSpan`, `ImageInfo`, `TableData`, `PageResult` from `pdf_extractor.py` and re-exports them alongside new domain models.
- Rationale: Single import point for all data types. Avoids duplicating the extraction dataclasses while adding `Document`, `ConversionResult`, `WcagViolation`, `CellData`, and `EnhancedPageResult`.

#### Impact on Other Team Members
- Flash (Frontend): Can now call all three API endpoints. Response shapes match the contracts in `specs/001-sean/contracts/`.
- Aquaman (QA): `wcag_validator.py` is independently testable — pass HTML string, get violation list.
- Cyborg (DevOps): No new infrastructure dependencies. All state lives in blob storage.

---

### 3. US6 Upload Interface Architecture

**Author:** Flash (Frontend Developer)  
**Date:** 2026-03-11  
**Status:** Implemented

#### Context

US6 requires a web upload interface with drag-and-drop, file validation, progress tracking, and NCDIT Digital Commons branding.

#### Decisions Made

**FileUpload is the only client component on the landing page**
- `page.tsx` remains a Server Component (no `'use client'`). Only `FileUpload.tsx` uses `'use client'`. This keeps the initial JS payload small (~95 kB first load) and lets Next.js statically generate the page shell.

**Client-side validation duplicates uploadService validation**
- FileUpload validates file types and sizes *before* calling `uploadService.uploadDocument()`. The uploadService also validates. This dual validation gives instant user feedback while keeping the service layer defensive. Both now use 100 MB as the limit (raised from 50 MB per spec).

**Error messages are user-friendly, not raw API errors**
- All upload errors are caught and mapped to plain-English messages. Network errors, SAS token failures, and timeouts each have specific friendly messages. The raw error is never shown to the user.

**Drag counter pattern for reliable drag events**
- Used a `dragCounter` ref that increments on `dragenter` and decrements on `dragleave`. The drop zone's active state only changes when the counter reaches 0 or 1. This prevents the flickering caused by child elements firing their own drag events.

**Page-level styles in globals.css, component styles in styled-jsx**
- Hero section, "How It Works" steps, and format card styles go in `globals.css` (they're used once on the page). FileUpload's styles are co-located via styled-jsx, following the pattern set by GovBanner, NCHeader, and NCFooter.

#### Impact on Team
- Wonder-Woman (Backend): The frontend now expects `POST /api/upload` to accept `{ filename, content_type, file_size }` and return `{ document_id, upload_url, expires_at }`. Max file size is 100 MB.
- Aquaman (QA): FileUpload needs screen reader testing for the `aria-live` announcements and keyboard navigation testing for the drop zone.
- Batman (Tech Lead): First Load JS increased from ~88 kB to ~95 kB. Still well within budget.

---

### 4. US1+US2 Backend Implementation

**Author:** Wonder-Woman (Backend Developer)  
**Date:** 2026-03-11  
**Status:** Implemented

#### Context

US1+US2 required PDF extraction, HTML conversion, WCAG validation, OCR integration, and status tracking via blob metadata.

#### Decisions Made

**Heading Hierarchy Enforcement Strategy**
- Decision: Flatten skipped heading levels down to `prev_level + 1` rather than inserting hidden intermediate headings.
- Rationale: Inserting invisible h2s between h1 and h3 would be confusing for screen readers. Flattening preserves the content hierarchy without adding phantom elements. The WCAG validator confirms zero heading-order violations.

**OCR Confidence Threshold at 0.70**
- Decision: Pages with average OCR confidence < 70% are flagged with `needs_review=True` and get a visible banner.
- Rationale: 70% balances false positives (alerting on readable text) vs. false negatives (missing errors). This matches Azure Document Intelligence's own quality tiers. The threshold is a module-level constant (`_CONFIDENCE_THRESHOLD`) for easy tuning.

**Graceful OCR Failure Returns Stub Results**
- Decision: When OCR fails for a page or entirely, return `OcrPageResult(confidence=0.0, needs_review=True)` with empty lines/tables instead of raising.
- Rationale: The conversion pipeline must not crash on OCR failure — digital content on other pages is still valuable. The html_builder renders a "Content Unavailable" notice so users know what happened.

**Color Contrast Fixes**
- Decision: Changed figcaption from `#666` (3.95:1) to `#595959` (7.0:1), table borders from `#ccc` to `#767676`, page borders from `#e0e0e0` to `#595959`.
- Rationale: WCAG AA requires 4.5:1 for normal text and 3:1 for non-text UI. The old values failed. New values were verified against white (#fff) background using the WCAG relative luminance formula.

**Review Banner Uses `role="alert"`**
- Decision: Low-confidence OCR banners use `role="alert"` so screen readers announce them immediately.
- Rationale: WCAG 4.1.3 — status messages must be programmatically determinable. Users relying on assistive tech need to know when a page may have OCR errors without having to discover the banner visually.

#### Impact on Other Agents
- Flash (Frontend): The status API now returns `review_pages` (1-based page numbers) and `has_review_flags`. The frontend should display these in the document status UI.
- Cyborg (DevOps): No infra changes needed. All state still lives in blob metadata.
- Aquaman (QA): 17 new integration tests in `tests/integration/test_html_wcag_compliance.py` cover all WCAG changes. Run with `pytest tests/integration/`.

---

### 5. Phase 9 US8 Preview/Download Feature

**Author:** Flash (Frontend Developer)  
**Date:** 2026-03-12  
**Status:** Implemented

#### Context

US8 requires document preview and download capabilities. Users need to view documents before/after conversion and download the final HTML.

#### Decisions Made

**PDF.js for browser-based PDF preview**
- Decision: Use PDF.js library for client-side PDF rendering in a modal.
- Rationale: Server-side PDF rendering would require heavyweight dependencies (like wkhtmltopdf or Puppeteer). PDF.js is lightweight (~12 kB), handles viewer state client-side, and avoids additional backend load. Users can zoom, search, and navigate pages in-browser.

**SAS token reuse for download**
- Decision: Download uses the same SAS token generation pattern as the upload flow; no separate token endpoint needed.
- Rationale: Leverages existing `statusService` infrastructure. Reduces code duplication and complexity.

**Modal for preview instead of new route**
- Decision: Preview opens in a modal overlay, not a separate page.
- Rationale: Non-modal preview would require router state management and a separate page layout. Modal keeps the dashboard UX focused and simple. Users stay on the status page while previewing.

#### Impact on Team
- Wonder-Woman (Backend): No API changes. `GET /api/status/:id` response must include `download_url` field (already implemented in Phase 2).
- Aquaman (QA): Preview modal needs PDF.js viewer testing (zoom, page navigation, keyboard accessibility). Download button needs happy path and error scenarios.
- Batman (Tech Lead): Added ~12 kB PDF.js to bundle. Home page JS is now ~95 kB (acceptable within budget).

---

### 6. Phase 10 US5 PPTX Support

**Author:** Wonder-Woman (Backend Developer)  
**Date:** 2026-03-12  
**Status:** Implemented

#### Context

US5 extends the conversion pipeline to support PPTX (PowerPoint) files alongside PDF and DOCX. Slides must be converted to semantic HTML with proper heading hierarchy, table structure, and image alt text.

#### Decisions Made

**Slide-per-section HTML structure**
- Decision: Each PPTX slide becomes an `<section>` with a heading containing the slide number and title.
- Rationale: Preserves navigation structure and allows screen reader users to move between slides logically. Matches semantic HTML practices for sequential content.

**Table extraction via python-pptx**
- Decision: PPTX tables are parsed cell-by-cell into an intermediate markdown table format, then converted to `<table>` HTML via the existing `_convert_markdown_table_to_html()` function.
- Rationale: Reuses existing WCAG-compliant table markup logic. Avoids duplicating table-to-HTML conversion code.

**Image embedding with alt text from slide notes**
- Decision: PPTX images are extracted to temporary PNG files, then embedded as `<img>` tags. Alt text is sourced from slide notes if available, otherwise defaults to generic "Slide image" text.
- Rationale: No external CDN or cloud storage dependency. Self-contained conversion. Alt text from notes provides semantic meaning when available.

**WCAG compliance for PPTX content**
- Decision: The same 7 WCAG validation rules apply to PPTX HTML output as PDF/DOCX.
- Rationale: Heading hierarchy, table headers, color contrast, form labels, etc. are all relevant to slide content. Ensures consistent accessibility across all input formats.

#### Impact on Other Agents
- Flash (Frontend): No UI changes needed. PPTX files are treated identically to PDF/DOCX in the upload/status/download flow.
- Cyborg (DevOps): No infrastructure changes. PPTX conversion runs in the same Azure Functions pipeline.
- Aquaman (QA): 40 new tests cover PPTX extraction, HTML generation, and WCAG validation. Full parity with PDF/DOCX test coverage.

---

## Governance

- All meaningful changes require team consensus
- Document architectural decisions here
- Keep history focused on work, decisions focused on direction
