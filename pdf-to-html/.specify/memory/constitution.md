<!-- Sync Impact Report
  Version change: 1.0.0 → 2.0.0
  Bump rationale: MAJOR — complete redefinition of principles to align with
    NC IDIT accessibility compliance requirements from stakeholder meeting
  Modified principles:
    - I. Modular Pipeline Architecture → I. WCAG 2.1 AA Compliance (NON-NEGOTIABLE)
    - II. Selective OCR Processing → II. Multi-Format Ingestion
    - III. Accessibility-First Output → III. Selective OCR for Legacy Documents
    - IV. Test-First Development → IV. Accessible Semantic Output
    - V. Cloud-Native Resilience → V. Batch Processing at Scale
    - VI. Fidelity & Accuracy → VI. Modular Pipeline Architecture
    - (new) VII. Test-First Development
    - (new) VIII. Cloud-Native Resilience
  Added sections:
    - Regulatory Context
    - Multi-Format Ingestion principle
    - Batch Processing at Scale principle
  Removed sections: None (reorganized)
  Templates requiring updates:
    - .specify/templates/plan-template.md ⚠ pending
    - .specify/templates/spec-template.md ⚠ pending
    - .specify/templates/tasks-template.md ⚠ pending
  Follow-up TODOs: None
-->

# pdf-to-html Constitution

## Regulatory Context

This project exists to meet a **DOJ ruling** requiring all content published
on North Carolina state websites to be **fully accessible by April 2026**.
The compliance standard is **WCAG 2.1 Level AA** under **Title II ADA**
digital accessibility requirements.

The document corpus includes:

- Scanned documents dating from the 1990s
- Searchable/digital PDFs
- Converted Word documents
- Slide decks (PowerPoint presentations)
- Mixed-format documents combining scanned and digital pages

The timeline is extremely compressed. All architectural and implementation
decisions MUST prioritize shipping a compliant solution within weeks, not
months.

## Core Principles

### I. WCAG 2.1 AA Compliance (NON-NEGOTIABLE)

Every HTML document produced MUST meet WCAG 2.1 Level AA. This is the legal
standard driving the entire project. Non-compliant output is a project
failure.

- All text MUST be programmatically determinable (no text-as-image)
- Reading order MUST be logical and match visual presentation
- Color contrast MUST meet 4.5:1 ratio for normal text, 3:1 for large text
- All images MUST have meaningful `alt` text or be marked decorative
- Tables MUST have proper header associations (`scope`, `headers` attributes)
- Forms, if present, MUST have associated labels
- Document MUST have proper language declaration (`lang` attribute)
- Headings MUST follow a logical hierarchy (no skipping levels)
- Links MUST have descriptive text (no "click here")
- Content MUST be navigable by keyboard alone

### II. Multi-Format Ingestion

The system MUST handle the full range of document formats found on NC state
websites:

- **Scanned PDFs**: Image-only documents requiring full OCR extraction
- **Digital PDFs**: Text-extractable documents with preserved formatting
- **Mixed PDFs**: Documents combining scanned and digital pages
- **Word Documents (.docx)**: Direct conversion preserving structure
- **PowerPoint (.pptx)**: Slide-by-slide conversion with speaker notes

Each format MUST have a dedicated extractor module. New formats SHOULD be
addable without modifying existing extractors.

### III. Selective OCR for Legacy Documents

OCR MUST only be invoked for pages classified as scanned or image-only (fewer
than 20 characters of extractable text). Digital content MUST skip OCR to
optimize cost and processing time.

- Azure Document Intelligence `prebuilt-layout` model is the standard OCR
  provider
- OCR failures on individual pages MUST NOT block the entire document
- OCR results MUST include confidence scores where available
- Legacy documents from the 1990s may have poor scan quality — the system
  MUST handle low-confidence OCR gracefully and flag pages that need human
  review

### IV. Accessible Semantic Output

All generated HTML MUST use semantic markup that supports assistive
technologies:

- HTML5 semantic elements: `h1`–`h6`, `p`, `ul`/`ol`, `li`, `table`,
  `figure`, `figcaption`, `nav`, `main`, `article`, `section`
- ARIA attributes where semantic HTML alone is insufficient
- Table headers MUST use `scope="col"` / `scope="row"` with proper
  `rowspan`/`colspan` support
- Skip navigation links for multi-page documents
- Document structure MUST be exposed via heading hierarchy
- Content MUST be reflowable and responsive (no fixed-width layouts)
- Output MUST be valid, well-formed HTML5 that passes automated WCAG
  validation tools (axe-core, WAVE)

### V. Batch Processing at Scale

Given the volume of documents on NC state websites and the compressed
timeline, the system MUST support efficient batch processing:

- Azure Functions blob trigger for automatic processing of uploaded documents
- Parallel processing of multiple documents simultaneously
- Progress tracking and reporting for batch operations
- Failed documents MUST be logged and retried without blocking the batch
- Processing status MUST be queryable (pending, processing, completed, failed)
- Output organization: `converted/{name}/{name}.html` with associated assets

### VI. Modular Pipeline Architecture

Every processing stage MUST be a self-contained module with clear
input/output contracts:

- **Extractors**: Format-specific modules (PDF, DOCX, PPTX) producing a
  common intermediate representation
- **OCR Service** (`ocr_service.py`): Handle scanned content via Azure
  Document Intelligence
- **HTML Builder** (`html_builder.py`): Convert intermediate representation
  into WCAG-compliant semantic HTML
- **Orchestrator** (`function_app.py`): Azure Functions entry point
  coordinating the pipeline

Modules MUST be independently testable. No module may directly depend on
Azure Functions runtime — all Azure service interactions MUST be injectable.

### VII. Test-First Development (NON-NEGOTIABLE)

All new features and bug fixes MUST follow a test-first workflow:

- Tests written before implementation code
- Red-Green-Refactor cycle strictly enforced
- WCAG compliance tests MUST be included for all output (automated axe-core
  validation)
- Edge cases MUST be covered: malformed PDFs, multi-language documents,
  large files, corrupted images, empty pages, 1990s-era scanned documents
- Accessibility regression tests MUST run in CI

### VIII. Cloud-Native Resilience

The application MUST be stateless and horizontally scalable:

- No state persisted between Azure Functions invocations
- All configuration via environment variables: `AzureWebJobsStorage`,
  `DOCUMENT_INTELLIGENCE_ENDPOINT`, `OUTPUT_CONTAINER`
- Authentication MUST use Azure Identity (`DefaultAzureCredential`)
- Errors MUST be logged with sufficient context for debugging
- Graceful degradation: individual page/document failures MUST NOT fail
  the entire batch

## Technology Stack Requirements

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| Runtime | Azure Functions (Python) | Serverless, event-driven, scales to zero |
| PDF Parsing | PyMuPDF (fitz) | Fast, comprehensive PDF extraction |
| OCR | Azure Document Intelligence | Enterprise-grade, layout-aware OCR |
| Storage | Azure Blob Storage | Native Azure Functions integration |
| Auth | Azure Identity (Entra ID) | Zero-secret managed identity |
| Output | HTML5 + inline CSS | Self-contained, WCAG-compliant documents |
| WCAG Validation | axe-core | Automated accessibility testing |
| Frontend | React / Next.js | Component-based UI with SSR capability |
| UI Design | frontend-design skill | Production-grade, distinctive aesthetics |
| DOCX Parsing | python-docx (planned) | Word document extraction |
| PPTX Parsing | python-pptx (planned) | PowerPoint extraction |

File organization:

```
Input:  files/{name}.{pdf,docx,pptx}
Output: converted/{name}/{name}.html
        converted/{name}/images/page{N}_img{M}.{ext}
```

## Development Workflow

1. **Specification**: Use GitHub Spec Kit to define requirements
2. **Branch**: Feature branch from `main`
3. **Test**: Write tests first — including WCAG validation tests
4. **Implement**: Minimal code to pass tests
5. **Validate**: Automated WCAG 2.1 AA check on all HTML output
6. **Review**: PR review with accessibility compliance verification
7. **Document**: Update squad decision logs

Squad members follow routing in `.squad/routing.md`. Tech Lead (Batman)
triages and enforces standards.

## Governance

This constitution supersedes all other development practices. Amendments
require:

1. Written proposal with rationale
2. Review by Tech Lead (Batman)
3. Semantic version bump:
   - **MAJOR**: Principle removal or backward-incompatible change
   - **MINOR**: New principle or expanded guidance
   - **PATCH**: Clarifications or wording fixes
4. Updated Sync Impact Report
5. Template propagation check in `.specify/templates/`

All PRs MUST verify WCAG 2.1 AA compliance. The April 2026 DOJ deadline
is immovable — scope decisions MUST favor shipping compliant output on time.

**Version**: 2.0.0 | **Ratified**: 2026-03-11 | **Last Amended**: 2026-03-11
