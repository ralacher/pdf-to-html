# PDF to HTML Converter

An Azure Function that converts PDF documents into accessible, semantic HTML. Built for the NC DIT accessibility initiative.

## How It Works

The pipeline has four stages:

1. **PDF Extraction** (`pdf_extractor.py`) — Uses PyMuPDF to extract text spans (with position, font, and style metadata), images, and tables. Classifies each page as digital (has selectable text) or scanned (image-only). Automatically removes repeated headers, footers, and page numbers.

2. **OCR for Scanned Pages** (`ocr_service.py`) — Sends scanned pages to Azure Document Intelligence (`prebuilt-layout` model) for OCR. Extracts text, tables, and reading order. Authenticates via Entra ID (`DefaultAzureCredential`) — no API keys.

3. **HTML Generation** (`html_builder.py`) — Converts extracted content into semantic HTML with proper headings, paragraph structure, bullet lists, accessible tables (`<thead>`, `<th scope>`), and images. Applies heuristics for heading detection (by font size), bullet list recognition, and multi-line bullet continuation.

4. **Output** (`function_app.py`) — The Azure Function is triggered when a PDF is uploaded to the `files` blob container. The converted HTML and extracted images are written to the `converted` container.

## Architecture

```
Blob Storage (files/{name}.pdf)
        │
        ▼
  Azure Function (Blob Trigger)
        │
        ├── PyMuPDF: extract text, images, tables
        │
        ├── Azure Document Intelligence (scanned pages only)
        │
        ├── Build semantic HTML
        │
        └── Upload to Blob Storage (converted/)
```
### Diagram 
<img width="960" height="431" alt="065a24d5-b2b8-4369-9117-1c2d3199fa7c" src="https://github.com/user-attachments/assets/8d3c839c-e65e-4bb6-bda0-9986a953a3cb" />

## Prerequisites

- Python 3.10+
- [Azure Functions Core Tools](https://learn.microsoft.com/azure/azure-functions/functions-run-tools?tabs=v4)
- [Azurite](https://learn.microsoft.com/azure/storage/common/storage-use-azurite) (for local blob storage emulation)
- Azure Document Intelligence resource (for OCR of scanned pages)
  - Must have Entra ID authentication enabled
  - Your identity needs `Cognitive Services User` role on the resource

## Getting Started

### 1. Clone and create virtual environment

```powershell
git clone <repo-url>
cd nc-dit-pdf_to_html
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure local settings

Edit `local.settings.json`:

```json
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "OUTPUT_CONTAINER": "converted",
    "DOCUMENT_INTELLIGENCE_ENDPOINT": "https://<your-resource>.cognitiveservices.azure.com/"
  }
}
```

### 3. Run locally (without Azure Functions)

The easiest way to test is with the local test script — no Azurite or Function host needed:

```powershell
python scripts/test_local.py .\input\sample.pdf
```

Output is written to `output/<pdf_name>/`.

### 4. Run with Azure Functions

Start Azurite (all 3 services: blob, queue, table), then:

```powershell
func start
```

Upload a PDF to the `files` blob container to trigger processing.

## Project Structure

```
function_app.py        — Azure Function entry point (blob trigger)
pdf_extractor.py       — PyMuPDF text/image/table extraction + header/footer removal
ocr_service.py         — Azure Document Intelligence OCR (Entra ID auth)
html_builder.py        — Semantic HTML generation
requirements.txt       — Python dependencies
host.json              — Azure Functions host configuration
local.settings.json    — Local environment variables
scripts/               — Helper scripts (see below)
```

## Helper Scripts

All scripts are in the `scripts/` directory.

### `test_local.py` — Local Pipeline Runner

Runs the full extraction → OCR → HTML pipeline locally without Azure Functions or Blob Storage.

```powershell
python scripts/test_local.py <input.pdf> [output_dir]
# Example:
python scripts/test_local.py .\input\report.pdf
# Output: output/report/report.html + output/report/images/
```

### `dump_pdf_text.py` — Text Dump for LLM

Extracts PDF content to a plain text file (with aligned tables), suitable for pasting into an LLM.

```powershell
python scripts/dump_pdf_text.py <input.pdf> [output.txt]
# Example:
python scripts/dump_pdf_text.py .\input\schedule.pdf
# Output: output/schedule.txt
```

### `test_layout.py` — pymupdf4llm Layout Comparison

Uses the `pymupdf4llm` layout engine to extract content as Markdown with images. Useful for comparing output quality against the main pipeline.

```powershell
pip install pymupdf4llm  # one-time install
python scripts/test_layout.py <input.pdf> [output_dir]
# Example:
python scripts/test_layout.py .\input\brochure.pdf
# Output: output/brochure_layout/brochure.md + output/brochure_layout/images/
```

### `debug_spans.py` — Span Inspector

Ad-hoc debugging script for inspecting raw PyMuPDF text spans and table detection on a specific PDF page. Edit the script to point at the PDF and page you want to inspect.

## Key Features

- **Hybrid extraction**: PyMuPDF for digital pages, Azure Document Intelligence for scanned pages
- **Accessible HTML output**: semantic headings, proper list markup, accessible tables
- **Header/footer removal**: automatically strips repeated text in page margins and page numbers
- **Text deduplication**: handles PDFs with shadow/outline text layers
- **Table detection**: extracts tables from both digital (PyMuPDF) and scanned (Document Intelligence) pages
- **Bullet list recognition**: detects and preserves bulleted/numbered lists with multi-line continuation
- **Entra ID authentication**: no API keys — uses `DefaultAzureCredential` for Document Intelligence
