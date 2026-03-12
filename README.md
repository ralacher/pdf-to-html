<div align="center">

<img src="https://files.nc.gov/digital-solutions/styles/_inline_extra_large_/public/images/2025-02/2021.08.09%20NCDIT%20Logo_White.png" alt="NCDIT Logo" width="280" />

# 📄 pdf-to-html

### WCAG 2.1 AA Compliant Document-to-HTML Converter

*An Azure Functions-powered document conversion service for the State of North Carolina*

[![WCAG 2.1 AA](https://img.shields.io/badge/WCAG-2.1_AA-green?style=for-the-badge&logo=w3c&logoColor=white)](https://www.w3.org/WAI/WCAG21/quickref/)
[![ADA Title II](https://img.shields.io/badge/ADA-Title_II-blue?style=for-the-badge)](https://www.ada.gov/law-and-regs/title-ii-2010-regulations/)
[![Azure Functions](https://img.shields.io/badge/Azure-Functions-0078D4?style=for-the-badge&logo=azure-functions&logoColor=white)](https://azure.microsoft.com/en-us/products/functions)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Next.js 14](https://img.shields.io/badge/Next.js-14-000000?style=for-the-badge&logo=next.js&logoColor=white)](https://nextjs.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge)](LICENSE)

---

**🏛️ Built for NC State Government** · **♿ Accessibility First** · **⚡ Serverless at Scale**

</div>

---

## 🎯 Mission

Convert PDF, Word, and PowerPoint documents published on North Carolina state websites into **fully accessible HTML** — meeting the **DOJ April 2026 deadline** for WCAG 2.1 Level AA compliance under **Title II ADA** digital accessibility requirements.

## 📊 Project Status

| Milestone | Status | Progress |
|-----------|--------|----------|
| 📋 Specification | ✅ Complete | ![100%](https://img.shields.io/badge/100%25-brightgreen?style=flat-square) |
| 📐 Architecture | ✅ Complete | ![100%](https://img.shields.io/badge/100%25-brightgreen?style=flat-square) |
| 🗺️ Implementation Plan | ✅ Complete | ![100%](https://img.shields.io/badge/100%25-brightgreen?style=flat-square) |
| ✅ Task Breakdown | ✅ Complete | ![100%](https://img.shields.io/badge/100%25-brightgreen?style=flat-square) |
| 🔧 Backend (PDF+OCR) | ✅ Complete | ![100%](https://img.shields.io/badge/100%25-brightgreen?style=flat-square) |
| 📝 DOCX Support | ✅ Complete | ![100%](https://img.shields.io/badge/100%25-brightgreen?style=flat-square) |
| 📊 PPTX Support | ✅ Complete | ![100%](https://img.shields.io/badge/100%25-brightgreen?style=flat-square) |
| 🌐 Web UI | ✅ Complete | ![100%](https://img.shields.io/badge/100%25-brightgreen?style=flat-square) |
| 🧪 Test Suite (444+ tests) | ✅ Complete | ![100%](https://img.shields.io/badge/100%25-brightgreen?style=flat-square) |
| 🤖 CI/CD & Eval Suite | ✅ Complete | ![100%](https://img.shields.io/badge/100%25-brightgreen?style=flat-square) |

### 📋 User Stories Implementation

| ID | Story | Status |
|----|-------|--------|
| US-01 | Convert Digital PDF to Accessible HTML | ✅ Complete |
| US-02 | Convert Scanned Legacy PDF with OCR | ✅ Complete |
| US-03 | Batch Process Multiple Documents | ✅ Complete |
| US-04 | Convert Word Documents to Accessible HTML | ✅ Complete |
| US-05 | Convert PowerPoint to Accessible HTML | ✅ Complete |
| US-06 | Upload Documents via Web Interface | ✅ Complete |
| US-07 | Track Conversion Progress in Real-Time | ✅ Complete |
| US-08 | Preview and Download Converted HTML | ✅ Complete |

## ✨ Features

| Feature | Description | Priority |
|---------|-------------|----------|
| 📄 **Digital PDF Conversion** | Extract text, headings, tables, images → WCAG HTML | P1 🎯 |
| 🔍 **Scanned PDF + OCR** | Azure Document Intelligence for legacy 1990s documents | P1 🎯 |
| 🖱️ **Web Upload Interface** | Drag-and-drop upload with NCDIT Digital Commons branding | P1 🎯 |
| 📦 **Batch Processing** | Process hundreds of documents concurrently | P2 |
| 📊 **Live Dashboard** | Real-time conversion progress tracking | P2 |
| 📝 **Word (.docx)** | Preserve Word document structure in HTML | P2 |
| 👁️ **Preview & Download** | In-browser HTML preview + zip package download | P2 |
| 📊 **PowerPoint (.pptx)** | Slide-by-slide HTML with speaker notes | P3 |

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│               🌐 Next.js 14 Web Interface                   │
│         React 18 • Bootstrap 5 • NCDIT Commons              │
│    Drag-drop upload • Live progress • Preview • Download    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────────┐  │
│  │ Upload   │  │ Status   │  │ Download │  │ Health    │  │
│  │ SAS API  │  │ Polling  │  │ SAS URLs │  │ Check API │  │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └─────┬─────┘  │
│       │              │             │              │        │
├───────┴──────────────┴─────────────┴──────────────┴────────┤
│            ⚡ Azure Functions v4 (Python 3.12)              │
│              Blob Trigger • HTTP Endpoints                  │
├─────────────────────────────────────────────────────────────┤
│                    📄 Document Extractors                   │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ PDF Extract  │  │ DOCX Extract │  │ PPTX Extractor   │  │
│  │ • PyMuPDF    │  │ • python-docx│  │ • python-pptx    │  │
│  │ • Text spans │  │ • Styles     │  │ • Slide-by-slide │  │
│  │ • Tables     │  │ • Tables     │  │ • Speaker notes  │  │
│  │ • Images     │  │ • Images     │  │ • Images         │  │
│  │ • Header/    │  │ • Header     │  │ • Tables         │  │
│  │   footer rm  │  │   inference  │  │ • Charts         │  │
│  └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘  │
│         │                 │                   │            │
│         └─────────────────┼───────────────────┘            │
│                           ▼                                │
│  ┌─────────────────────────────────────────────────────┐   │
│  │        🔍 Azure Document Intelligence OCR           │   │
│  │     (scanned PDF pages only, <20 chars text)        │   │
│  │     prebuilt-layout model • confidence scoring      │   │
│  └───────────────────────┬─────────────────────────────┘   │
│                          ▼                                 │
│  ┌─────────────────────────────────────────────────────┐   │
│  │          ♿ Semantic HTML Builder                    │   │
│  │    • WCAG 2.1 AA compliant HTML5                    │   │
│  │    • Heading hierarchy enforcement                  │   │
│  │    • Table scope attributes                         │   │
│  │    • Image alt text derivation                      │   │
│  │    • Skip nav • Landmarks • Focus indicators        │   │
│  │    • Low-confidence review banners                  │   │
│  │    • Inline CSS (self-contained output)             │   │
│  └───────────────────────┬─────────────────────────────┘   │
│                          ▼                                 │
│  ┌─────────────────────────────────────────────────────┐   │
│  │          ✅ WCAG Validator (Python)                  │   │
│  │    • 7 server-side compliance rules                 │   │
│  │    • Alt text • Heading order • Table headers       │   │
│  │    • Language attribute • Skip nav • Contrast       │   │
│  └───────────────────────┬─────────────────────────────┘   │
│                          ▼                                 │
│  ┌─────────────────────────────────────────────────────┐   │
│  │          📦 Azure Blob Storage                       │   │
│  │    • files/ (user uploads via SAS token)            │   │
│  │    • converted/ (HTML + images + metadata.json)     │   │
│  │    • Status tracking via blob metadata              │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## 🚀 Quick Start

### Prerequisites

- Python 3.12+
- Node.js 20+
- Azure Functions Core Tools v4
- Azurite (local blob storage emulator)

### Backend

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export AzureWebJobsStorage="UseDevelopmentStorage=true"
export DOCUMENT_INTELLIGENCE_ENDPOINT="https://<your-resource>.cognitiveservices.azure.com/"
export OUTPUT_CONTAINER="converted"

# Start local storage emulator
azurite-blob --silent &

# Start Azure Functions
func start
```

### Frontend

```bash
cd frontend
npm install
npm run dev
# Open http://localhost:3000
```

### Convert a Document

```bash
# Upload via CLI
az storage blob upload \
  --container-name files \
  --file my-document.pdf \
  --name my-document.pdf \
  --connection-string "UseDevelopmentStorage=true"

# Or drag-and-drop via the web UI at http://localhost:3000
```

## 🧪 Testing

**444+ Tests Across All Layers**

### Backend Tests (137 Python tests)
```bash
# Run all backend tests
pytest tests/ -v

# Run with coverage report
pytest tests/ -v --cov=. --cov-report=html

# Run specific test suites
pytest tests/unit/ -v                    # Unit tests (extractors, validators, builders)
pytest tests/integration/ -v             # Integration tests (full pipelines)
pytest tests/ -k "wcag" -v              # WCAG compliance tests only
```

### Frontend Tests (307 test cases)
```bash
cd frontend

# Linting and type checking
npm run lint

# Build verification (catches TypeScript errors)
npm run build

# Run Next.js test suite
npm test

# Accessibility testing
npm run test:a11y
```

### WCAG Evaluation Suite
The project includes a comprehensive WCAG 2.1 AA evaluation suite that runs on every PR:
- Converts real-world test documents (PDFs, DOCX, PPTX)
- Validates heading hierarchy, table accessibility, image alt coverage
- Generates compliance reports with violation details
- Automatically posts results to PR comments
- CI workflow: `.github/workflows/eval.yml`

```bash
# Run eval suite locally
python scripts/run_evals.py --output tests/eval/results/eval-report.json
python scripts/render_report.py --input tests/eval/results/eval-report.json --output tests/eval/results/eval-report.md
```

## 🦸 Squad (Justice League)

This project uses [Squad](https://github.com/bradygaster/squad) for AI-assisted team coordination.

| Agent | Role | Domain |
|-------|------|--------|
| 🦇 **Batman** | Tech Lead | Architecture, code review, triage |
| 🛡️ **Wonder-Woman** | Backend Developer | PDF/DOCX/PPTX extraction, OCR, Azure Functions |
| ⚡ **Flash** | Frontend Developer | React/Next.js UI, NCDIT Digital Commons styling |
| 🤖 **Cyborg** | DevOps & Infrastructure | Azure deployment, CI/CD, monitoring |
| 🔱 **Aquaman** | QA & Testing | WCAG validation, test coverage, edge cases |
| 📝 **Scribe** | Documentation | Session logging, decision records |

## 📋 Spec Kit

This project uses [GitHub Spec Kit](https://github.com/github/spec-kit) for specification-driven development.

| Artifact | Path | Description |
|----------|------|-------------|
| 📜 Constitution | `pdf-to-html/.specify/memory/constitution.md` | Project principles (v2.0.0) |
| 📋 Specification | `specs/001-sean/spec.md` | Feature spec (8 user stories, 25 FRs) |
| 🗺️ Plan | `specs/001-sean/plan.md` | Implementation plan |
| 🔬 Research | `specs/001-sean/research.md` | Technology decisions |
| 📊 Data Model | `specs/001-sean/data-model.md` | Entity definitions |
| 🔌 API Contracts | `specs/001-sean/contracts/` | Upload, Status, Download APIs |
| ✅ Tasks | `specs/001-sean/tasks.md` | 79 actionable implementation tasks |

## 🐳 Container Apps Architecture

> **Migration complete** — the backend has been migrated from Azure Functions to Azure Container Apps (FastAPI + queue worker).

| Component | Technology | Entry Point |
|-----------|-----------|-------------|
| **HTTP API** | FastAPI + Uvicorn | `app/main.py` |
| **Queue Worker** | Azure Storage Queue polling | `app/worker.py` |
| **Frontend** | Next.js 14 (standalone) | `frontend/` |
| **Local Storage** | Azurite emulator | `docker-compose.yml` |
| **Infrastructure** | Bicep IaC | `infra/` |

### Local Development

```bash
# Recommended: all services in one command
docker-compose up --build

# Services:
#   Frontend:  http://localhost:3000
#   Backend:   http://localhost:8000
#   Azurite:   ports 10000-10002
```

Or run each process manually — see [`MIGRATION.md`](MIGRATION.md) for the 4-terminal setup.

For full migration details, rollback procedure, and environment variables, see:
- [`MIGRATION.md`](MIGRATION.md)
- [`specs/004-container-apps-migration/plan.md`](specs/004-container-apps-migration/plan.md)

## 📌 Dependency Versions

> Pulled from `requirements.txt`, `frontend/package.json`, and `host.json`

| Component | Package | Version | Notes |
|-----------|---------|---------|-------|
| **⚡ Runtime** | Azure Functions SDK | `1.24.0` | Python worker |
| **⚡ Runtime** | Extension Bundle | `[4.*, 5.0.0)` | host.json |
| **🐍 Python** | Python | `3.12+` | Required minimum |
| **📄 PDF** | PyMuPDF | `1.27.2` | Text, image, table extraction |
| **🔍 OCR** | Azure AI Document Intelligence | `1.0.2` | Scanned PDF recognition |
| **🔐 Auth** | Azure Identity | `1.25.2` | Managed identity / Entra ID |
| **☁️ Storage** | Azure Storage Blob | `12.28.0b1` | Input/output persistence |
| **📝 DOCX** | python-docx | `1.2.0` | Word document extraction |
| **📊 PPTX** | python-pptx | `1.0.2` | PowerPoint extraction |
| **🎨 Templates** | Jinja2 | `3.1.6` | HTML templating |
| **🧪 Testing** | pytest | `9.0.2` | Test framework |
| **🧪 Testing** | pytest-cov | `7.0.0` | Coverage reporting |
| **🧪 Testing** | pytest-asyncio | `1.3.0` | Async test support |
| **🌐 Frontend** | Next.js | `14.2.35` | React framework with SSR |
| **⚛️ UI** | React | `^18` | Component library |
| **🎨 Styling** | Bootstrap | `^5.3.8` | NCDIT Digital Commons compatible |
| **♿ A11y** | axe-core | `^4.11.1` | WCAG automated testing |
| **📦 Archive** | JSZip | `^3.10.1` | Download package creation |
| **🔧 TypeScript** | TypeScript | `^5` | Type-safe frontend |
| **🧪 Frontend Test** | Jest | `^30.3.0` | Frontend test runner |
| **🔍 Lint** | ESLint | `8.57.1` | Code quality |

## 📦 Release History

| Version | Date | Component | Changes |
|---------|------|-----------|---------|
| v0.4.0 | 2026-03-11 | 📋 Tasks | 79 implementation tasks generated with squad assignments |
| v0.3.0 | 2026-03-11 | 🗺️ Plan | Implementation plan, research, data model, API contracts |
| v0.2.0 | 2026-03-11 | 📋 Spec | 8 user stories, 25 FRs, NCDIT Digital Commons UI requirements |
| v0.1.0 | 2026-03-11 | 📜 Constitution | v2.0.0 — WCAG 2.1 AA, multi-format, batch processing principles |
| v0.0.1 | 2026-03-11 | 🏗️ Scaffold | Project init, Squad (Justice League), Spec Kit, frontend-design skill |

## 🛠️ Technology Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| ⚡ Runtime | Azure Functions (Python 3.12) | Serverless document processing |
| 📄 PDF | PyMuPDF (fitz) | Digital PDF text/image/table extraction |
| 🔍 OCR | Azure Document Intelligence | Scanned page recognition (prebuilt-layout) |
| 📝 DOCX | python-docx | Word document structure extraction |
| 📊 PPTX | python-pptx | PowerPoint slide extraction |
| ♿ Validation | axe-core | Automated WCAG 2.1 AA compliance testing |
| 🌐 Frontend | React 18 / Next.js 14 | Component-based web UI with SSR |
| 🎨 UI Framework | Bootstrap 5 | NCDIT Digital Commons compatible |
| 🏛️ Design System | NCDIT Digital Commons | NC.gov brand compliance |
| ☁️ Storage | Azure Blob Storage | Document input/output persistence |
| 🔐 Auth | Azure Identity (Entra ID) | Managed identity, zero secrets |

## 📁 Project Structure

```
pdf-to-html/
├── 📄 function_app.py          # Azure Functions orchestrator (blob trigger, HTTP APIs)
├── 📦 requirements.txt         # Python dependencies
├── ⚙️ host.json                # Azure Functions configuration
│
├── 🔧 backend/                 # Python backend package
│   ├── 📄 pdf_extractor.py     # PDF → text/images/tables (PyMuPDF)
│   ├── 📝 docx_extractor.py    # Word document extraction (python-docx)
│   ├── 📊 pptx_extractor.py    # PowerPoint extraction (python-pptx)
│   ├── 🔍 ocr_service.py       # Azure Document Intelligence OCR client
│   ├── ♿ html_builder.py       # WCAG-compliant HTML generation
│   ├── ✅ wcag_validator.py     # Server-side WCAG 2.1 AA validation (7 rules)
│   ├── 📊 status_service.py    # Document processing status tracking
│   └── 📋 models.py            # Pydantic data models
│
├── 🌐 frontend/                # Next.js 14 React app
│   ├── app/                    # App Router (Next.js 13+)
│   ├── components/             # React components (GovBanner, NCHeader, UploadZone, etc.)
│   ├── services/               # API client services (upload, status, download)
│   └── styles/                 # NCDIT Digital Commons design tokens
│
├── 🧪 tests/
│   ├── unit/                   # Backend unit tests (174 tests)
│   ├── integration/            # End-to-end pipeline tests
│   ├── eval/                   # WCAG evaluation suite
│   └── conftest.py             # Pytest fixtures
│
├── 📖 docs/                    # Project documentation
│   ├── QUICKSTART.md           # Development setup guide
│   ├── DEPLOYMENT.md           # Azure deployment guide
│   └── runbook/                # Operations runbook
│
├── 🤖 .github/workflows/       # CI/CD workflows (eval.yml, squad automation)
├── 🦸 .squad/                  # Squad (Justice League) config
├── 📋 specs/001-sean/          # Spec Kit artifacts (spec, plan, tasks, contracts)
├── 🎨 .agents/skills/          # AI skills (frontend-design)
├── 📜 pdf-to-html/.specify/    # Spec Kit memory (constitution.md)
├── 🔧 scripts/                 # Automation scripts (quickstart-check, evals)
├── 📖 README.md                # This file
└── ⚙️ .env.example              # Environment variables template
```

## ♿ Accessibility Commitment

This project exists because **accessible government services are a civil right**. Every North Carolinian — regardless of ability — deserves equal access to public information.

- 🎯 **WCAG 2.1 Level AA** — the legal standard, our minimum bar
- 🔍 **Automated + manual testing** — axe-core catches ~57%, humans catch the rest
- 📋 **NC Digital Accessibility & Usability Standard v1.1** — our compliance framework
- ⚖️ **Title II ADA** — the law that drives this work
- 🗓️ **April 2026** — the deadline that makes it urgent

## 📜 Regulatory Context

> *All content published on North Carolina state websites must be fully accessible by April 2026, per DOJ ruling under Title II ADA digital accessibility requirements. The compliance standard is WCAG 2.1 Level AA.*

---

<div align="center">

**Built with ❤️ for the people of North Carolina**

🏛️ [NC.gov](https://www.nc.gov) · 💻 [NCDIT](https://it.nc.gov) · ♿ [Digital Accessibility](https://it.nc.gov/documents/digital-accessibility-usability-standard/open)

</div>

---

<sub>📅 Last Updated: 2025-07-24 · Maintained by 🦇 Batman (Tech Lead)</sub>
