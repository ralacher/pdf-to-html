# Feature Specification: WCAG-Compliant Document-to-HTML Converter

**Feature Branch**: `002-wcag-doc-converter`
**Created**: 2026-03-11
**Status**: Draft
**Input**: User description: "Convert PDF, DOCX, and PPTX documents to WCAG 2.1 AA compliant HTML for NC state website accessibility compliance"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Convert a Digital PDF to Accessible HTML (Priority: P1)

A state agency content manager uploads a digitally-created PDF (e.g., a Word
document saved as PDF) to the system. The system extracts text, headings,
tables, images, and lists from the PDF and produces a fully WCAG 2.1 AA
compliant HTML page. The manager can then publish this HTML on their state
website, confident it meets the DOJ April 2026 accessibility deadline.

**Why this priority**: Digital PDFs are the most common document type on state
websites and the extraction is most reliable. This delivers immediate value
for the largest portion of the document corpus.

**Independent Test**: Upload a multi-page PDF with headings, tables, images,
and lists. Verify the output HTML passes axe-core WCAG 2.1 AA validation
with zero violations.

**Acceptance Scenarios**:

1. **Given** a digital PDF is uploaded to the `files/` container, **When** the
   Azure Function processes it, **Then** a WCAG 2.1 AA compliant HTML file is
   created in `converted/{name}/{name}.html` with all text content preserved.
2. **Given** the PDF contains a data table with headers, **When** converted,
   **Then** the HTML table has proper `<th>` elements with `scope` attributes
   and maintains the correct row/column structure.
3. **Given** the PDF contains images, **When** converted, **Then** each image
   has a `<figure>` wrapper with `<figcaption>` and meaningful `alt` text
   derived from surrounding context.
4. **Given** the PDF has a heading hierarchy, **When** converted, **Then** the
   HTML uses `<h1>` through `<h6>` in logical order with no skipped levels.

---

### User Story 2 - Convert a Scanned Legacy PDF with OCR (Priority: P1)

A state agency uploads a scanned PDF from the 1990s (image-only, no
extractable text). The system detects it as scanned, sends it through OCR
using Azure Document Intelligence, and produces accessible HTML. Pages with
low OCR confidence are flagged for human review.

**Why this priority**: Legacy scanned documents represent a significant
portion of the corpus and are the hardest to make accessible. Without OCR,
these documents are completely inaccessible.

**Independent Test**: Upload a scanned PDF with mixed quality pages. Verify
text is extracted, HTML is WCAG compliant, and low-confidence pages are
flagged.

**Acceptance Scenarios**:

1. **Given** a scanned PDF with no extractable text, **When** processed,
   **Then** OCR extracts the text and produces HTML with all recognized
   content.
2. **Given** a mixed PDF with some digital and some scanned pages, **When**
   processed, **Then** only scanned pages go through OCR while digital pages
   are extracted directly.
3. **Given** a poorly scanned page with OCR confidence below 70%, **When**
   processed, **Then** the page is included in output but flagged with a
   visible notice recommending human review.
4. **Given** OCR fails on a single page, **When** processed, **Then** the
   remaining pages are still converted successfully and the failed page is
   logged.

---

### User Story 3 - Batch Process Multiple Documents (Priority: P2)

An agency administrator uploads a folder of 500 documents to the blob storage
container. The system processes each document automatically, tracks progress,
and produces a summary report showing which documents succeeded, failed, or
need human review.

**Why this priority**: The compressed timeline (weeks, not months) means
agencies need to convert large volumes of documents quickly. One-at-a-time
processing won't meet the April 2026 deadline.

**Independent Test**: Upload 10 documents of varying formats and quality.
Verify all are processed, status is tracked, and a completion summary is
available.

**Acceptance Scenarios**:

1. **Given** multiple documents are uploaded to `files/`, **When** the system
   processes them, **Then** each document is converted independently and
   failures do not block other documents.
2. **Given** a batch is in progress, **When** a user checks status, **Then**
   they can see how many documents are pending, processing, completed, and
   failed.
3. **Given** a batch completes, **When** the user reviews results, **Then** a
   summary report lists each document with its conversion status and any
   flagged issues.

---

### User Story 4 - Convert Word Documents to Accessible HTML (Priority: P2)

A content author uploads a .docx file. The system extracts the document
structure (headings, paragraphs, tables, images, lists) and produces
WCAG 2.1 AA compliant HTML, preserving the semantic structure from the
original Word document.

**Why this priority**: Word documents are the second most common format on
state websites. Their native structure (styles, headings) provides rich
semantic information for accessible HTML generation.

**Independent Test**: Upload a .docx with styled headings, tables, and
images. Verify the output HTML preserves structure and passes WCAG validation.

**Acceptance Scenarios**:

1. **Given** a .docx file is uploaded, **When** processed, **Then** the system
   produces WCAG 2.1 AA compliant HTML with headings, lists, and tables
   preserved from the original Word structure.
2. **Given** a .docx with embedded images, **When** processed, **Then** images
   are extracted and included with `alt` text derived from Word's alt text
   field or surrounding context.

---

### User Story 5 - Convert PowerPoint to Accessible HTML (Priority: P3)

A state agency uploads a .pptx presentation. The system converts each slide
to an HTML section with proper heading structure, preserving text, images,
tables, and speaker notes as accessible content.

**Why this priority**: Slide decks are less common than PDFs and Word docs
but still present on state websites. Speaker notes provide additional
accessible content.

**Independent Test**: Upload a .pptx with 10 slides including charts, tables,
and speaker notes. Verify slide-by-slide HTML output passes WCAG validation.

**Acceptance Scenarios**:

1. **Given** a .pptx file is uploaded, **When** processed, **Then** each slide
   becomes an HTML `<section>` with the slide title as a heading and content
   preserved semantically.
2. **Given** a slide has speaker notes, **When** processed, **Then** notes are
   included as accessible content associated with the slide.

---

### User Story 6 - Upload Documents via Web Interface (Priority: P1)

A state agency content manager opens the web application in their browser.
They drag and drop one or more documents (PDF, DOCX, PPTX) onto the upload
area, or click to browse and select files. The interface shows an upload
progress indicator for each file, confirms successful upload, and
automatically begins conversion. The web interface is itself WCAG 2.1 AA
compliant, with a distinctive, polished design that reflects the
professionalism of NC state government services.

**Why this priority**: Without a user-friendly upload interface, agencies
must interact directly with Azure Blob Storage, which requires technical
knowledge. A web UI is essential for non-technical content managers to use
the system independently.

**Independent Test**: Open the web app, drag a PDF onto the upload zone,
verify the file uploads with progress feedback and conversion begins
automatically.

**Acceptance Scenarios**:

1. **Given** the user opens the web app, **When** they drag a file onto the
   upload area, **Then** the file uploads with a visible progress bar and
   the conversion process starts automatically.
2. **Given** the user drops multiple files, **When** uploads complete,
   **Then** each file shows individual progress and status (uploading,
   queued, processing).
3. **Given** the user drops an unsupported file type (e.g., .zip), **When**
   the upload is attempted, **Then** the system rejects it with a clear
   error message listing supported formats.
4. **Given** the user is on a mobile device or uses assistive technology,
   **When** they interact with the upload interface, **Then** all
   functionality is accessible via keyboard and screen reader.

---

### User Story 7 - Track Conversion Progress in Real-Time (Priority: P2)

After uploading documents, the content manager sees a live dashboard showing
the status of each document: queued, processing, completed, or failed. They
can see which page is currently being processed for large documents and get
an estimated time remaining.

**Why this priority**: With hundreds of documents to convert under a tight
deadline, agencies need visibility into what's happening. A progress
dashboard reduces anxiety and helps plan workload.

**Independent Test**: Upload 5 documents and verify the dashboard updates
in real-time showing each document's status progression.

**Acceptance Scenarios**:

1. **Given** documents are being processed, **When** the user views the
   dashboard, **Then** they see real-time status for each document with
   a progress indicator.
2. **Given** a document fails conversion, **When** the user views the
   dashboard, **Then** the failed document shows an error description
   and a retry option.
3. **Given** all documents in a batch complete, **When** the user views
   the dashboard, **Then** they see a summary with counts of successful,
   failed, and flagged-for-review documents.

---

### User Story 8 - Preview and Download Converted HTML (Priority: P2)

After conversion completes, the content manager clicks on a completed
document to preview the generated HTML directly in the browser. They can
verify the output looks correct, check the WCAG compliance status, and
download the HTML file and associated images as a package.

**Why this priority**: Content managers need to verify output quality before
publishing to state websites. A preview reduces the feedback loop and
catches issues before they go live.

**Independent Test**: Complete a conversion, click preview, verify the HTML
renders correctly in the browser, and download the output package.

**Acceptance Scenarios**:

1. **Given** a document has been successfully converted, **When** the user
   clicks "Preview," **Then** the generated HTML renders in an iframe or
   new tab showing the accessible output.
2. **Given** the user reviews a preview, **When** they click "Download,"
   **Then** they receive a zip file containing the HTML and all associated
   image assets.
3. **Given** a converted document has pages flagged for human review,
   **When** the user previews it, **Then** flagged pages are visually
   highlighted with the confidence warning.

---

### Edge Cases

- What happens when a PDF is password-protected or encrypted? System MUST
  reject it with a clear error message indicating the document cannot be
  processed.
- How does the system handle a 500-page PDF? System MUST process it without
  timeout, using page-by-page processing with progress tracking.
- What happens when a document has no text content at all (e.g., a single
  large image)? System MUST run OCR and flag for human review if confidence
  is low.
- How does the system handle multi-language documents? System MUST preserve
  all text regardless of language and set appropriate `lang` attributes on
  content sections where language can be detected.
- What happens when a .docx uses non-standard formatting (no heading styles)?
  System MUST still produce valid HTML using font-size-based heading inference.
- What happens when the blob storage container is unreachable? System MUST
  retry with exponential backoff and log the failure.
- What happens when the user uploads a file larger than 100MB via the web UI?
  System MUST show a clear file size limit error before upload begins.
- What happens when the user's browser loses connection during upload? System
  MUST detect the interruption and allow the user to retry without
  re-selecting files.
- What happens when two users upload the same filename simultaneously? System
  MUST handle naming conflicts without overwriting or data loss.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST accept PDF files (.pdf) and produce WCAG 2.1 AA
  compliant HTML output.
- **FR-002**: System MUST detect scanned/image-only pages (fewer than 20
  characters of extractable text) and route them through OCR automatically.
- **FR-003**: System MUST use Azure Document Intelligence `prebuilt-layout`
  model for OCR processing of scanned pages.
- **FR-004**: System MUST produce semantic HTML5 with proper heading hierarchy
  (`h1`-`h6`), lists (`ul`/`ol`), tables with `scope` attributes, and
  figure/figcaption for images.
- **FR-005**: System MUST include skip navigation, document language
  declaration, and keyboard-navigable structure in all output.
- **FR-006**: System MUST extract and preserve data tables with header
  associations, rowspan, and colspan.
- **FR-007**: System MUST provide meaningful `alt` text for images derived
  from OCR text, captions, or surrounding context.
- **FR-008**: System MUST handle batch processing — multiple documents
  uploaded concurrently without interference.
- **FR-009**: System MUST flag pages with OCR confidence below 70% for human
  review with a visible notice in the output HTML.
- **FR-010**: System MUST log processing status for each document (pending,
  processing, completed, failed) queryable via storage metadata.
- **FR-011**: System MUST accept Word documents (.docx) and produce WCAG 2.1
  AA compliant HTML preserving document structure.
- **FR-012**: System MUST accept PowerPoint files (.pptx) and produce
  WCAG 2.1 AA compliant HTML with slide-by-slide sections.
- **FR-013**: System MUST reject password-protected or encrypted documents
  with a clear error message.
- **FR-014**: System MUST produce self-contained HTML with inline CSS — no
  external dependencies required for rendering.
- **FR-015**: System MUST organize output as
  `converted/{name}/{name}.html` with images in
  `converted/{name}/images/`.
- **FR-016**: System MUST ensure color contrast ratios meet WCAG AA minimums
  (4.5:1 normal text, 3:1 large text) in generated HTML styling.
- **FR-017**: System MUST provide a web interface with drag-and-drop file
  upload supporting PDF, DOCX, and PPTX formats.
- **FR-018**: Web interface MUST show real-time upload progress for each file
  with visual feedback (progress bar, status text).
- **FR-019**: Web interface MUST display a live dashboard showing conversion
  status for all documents (queued, processing, completed, failed).
- **FR-020**: Web interface MUST allow users to preview converted HTML output
  directly in the browser.
- **FR-021**: Web interface MUST allow users to download converted documents
  as a package (HTML + image assets).
- **FR-022**: Web interface MUST allow users to retry failed conversions
  without re-uploading the original document.
- **FR-023**: Web interface itself MUST be fully WCAG 2.1 AA compliant —
  keyboard navigable, screen reader compatible, proper contrast ratios.
- **FR-024**: Web interface MUST validate file types and sizes before upload,
  rejecting unsupported formats with clear error messages.
- **FR-025**: Web interface MUST use a distinctive, professional design
  befitting NC state government services — avoiding generic or template-like
  aesthetics. Apply the frontend-design skill for production-grade UI quality.

### Key Entities

- **Document**: An input file (PDF, DOCX, or PPTX) with metadata including
  name, format, size, upload timestamp, and processing status.
- **Page/Slide**: An individual unit within a document — a PDF page, a Word
  document section, or a PowerPoint slide — containing text, images, and
  tables.
- **Conversion Result**: The output HTML file and associated image assets,
  including WCAG compliance status and any human review flags.
- **OCR Result**: Text and layout data extracted from scanned pages, including
  per-page confidence scores and table structure.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of output HTML documents pass automated WCAG 2.1 AA
  validation (axe-core) with zero critical violations.
- **SC-002**: Digital PDF conversion completes within 30 seconds per 50-page
  document.
- **SC-003**: Scanned PDF conversion (with OCR) completes within 3 minutes
  per 50-page document.
- **SC-004**: System processes at least 100 documents concurrently without
  failures or resource exhaustion.
- **SC-005**: 95% or more of text content from source documents is accurately
  preserved in HTML output (measured by character-level comparison for digital
  PDFs).
- **SC-006**: All data tables in output maintain correct header-cell
  associations verifiable by automated accessibility testing.
- **SC-007**: Pages flagged for human review (low OCR confidence) represent
  less than 10% of total pages for documents scanned after 2000.
- **SC-008**: System achieves zero data loss — every successfully processed
  document produces complete HTML output with all text, tables, and images.
- **SC-009**: Web interface loads and is interactive within 3 seconds on a
  standard broadband connection.
- **SC-010**: Web interface itself passes automated WCAG 2.1 AA validation
  with zero critical violations.
- **SC-011**: Users can upload a document and see conversion begin within
  10 seconds of drop/selection.
- **SC-012**: 90% of first-time users can successfully upload a document and
  download the converted HTML without assistance or documentation.

## Assumptions

- Azure Document Intelligence service is provisioned and accessible via
  `DOCUMENT_INTELLIGENCE_ENDPOINT` environment variable.
- Azure Blob Storage containers (`files/` and `converted/`) exist and the
  function app has read/write access.
- The Azure Functions consumption plan provides sufficient concurrency for
  batch processing (or can be scaled to a premium plan if needed).
- Documents are uploaded in their original format — no pre-processing or
  format conversion is expected from users.
- Image alt text generation uses context-based inference (surrounding text,
  captions) rather than AI-based image description — true image description
  is out of scope for the initial release.
- The April 2026 DOJ deadline is the hard constraint — P1 stories (PDF
  conversion + web upload UI) MUST ship first, with P2/P3 (DOCX, PPTX,
  batch dashboard, preview/download) following as timeline permits.
- The web interface will be built with React/Next.js, deployed as a static
  web app or alongside the Azure Functions backend.
- The frontend-design skill (anthropics/skills/frontend-design) will be
  applied during implementation for distinctive, production-grade UI quality
  that avoids generic AI aesthetics.