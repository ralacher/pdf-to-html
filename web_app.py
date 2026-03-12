"""
Lightweight Flask web UI for the PDF-to-HTML converter.
Runs independently of the Azure Function — the function_app.py blob trigger
remains untouched and fully operational.

Usage:
    python web_app.py          # starts on http://localhost:5000
    python web_app.py --port 8080
"""

import io
import logging
import os
import sys
import time
import zipfile

from flask import Flask, request, jsonify, send_from_directory, Response

from pdf_extractor import extract_pdf
from html_builder import build_html

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder="static", static_url_path="/static")

MAX_UPLOAD_MB = 50
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/convert", methods=["POST"])
def convert_pdf():
    """Accept a PDF upload, run the pipeline, return HTML + images as a zip."""
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        return jsonify({"error": "File must be a PDF"}), 400

    pdf_data = file.read()
    if not pdf_data:
        return jsonify({"error": "Uploaded file is empty"}), 400

    pdf_name = os.path.splitext(file.filename)[0]
    logger.info("Converting: %s (%d bytes)", file.filename, len(pdf_data))

    try:
        t0 = time.perf_counter()

        # Step 1: Extract
        pages, metadata = extract_pdf(pdf_data)

        # Step 2: OCR scanned pages (if DI is configured)
        ocr_results = {}
        scanned_pages = [p.page_number for p in pages if p.is_scanned]
        if scanned_pages:
            endpoint = os.environ.get("DOCUMENT_INTELLIGENCE_ENDPOINT", "")
            if endpoint:
                from ocr_service import ocr_pdf_pages
                ocr_results = ocr_pdf_pages(pdf_data, scanned_pages)

        # Step 3: Build HTML with embedded images for preview, external for download
        html_content, image_files = build_html(
            pages=pages,
            ocr_results=ocr_results,
            metadata=metadata,
            embed_images=True,
        )

        # Also build a version with external image references for download
        html_download, image_files_download = build_html(
            pages=pages,
            ocr_results=ocr_results,
            metadata=metadata,
            embed_images=False,
        )

        elapsed = time.perf_counter() - t0
        logger.info("Converted in %.2fs — %d pages, %d images", elapsed, len(pages), len(image_files_download))

        # Build a zip for download
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(f"{pdf_name}.html", html_download.encode("utf-8"))
            for img_name, img_bytes in image_files_download.items():
                zf.writestr(f"images/{img_name}", img_bytes)
        zip_bytes = zip_buffer.getvalue()

        return jsonify({
            "html": html_content,
            "filename": pdf_name,
            "pages": len(pages),
            "digital_pages": sum(1 for p in pages if not p.is_scanned),
            "scanned_pages": len(scanned_pages),
            "ocr_available": bool(os.environ.get("DOCUMENT_INTELLIGENCE_ENDPOINT")),
            "images": len(image_files_download),
            "elapsed": round(elapsed, 2),
            "zip_size": len(zip_bytes),
        })

    except Exception as e:
        logger.exception("Conversion failed")
        return jsonify({"error": str(e)}), 500


@app.route("/api/download", methods=["POST"])
def download_zip():
    """Re-run conversion and return a downloadable zip."""
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]
    pdf_data = file.read()
    pdf_name = os.path.splitext(file.filename or "document")[0]

    pages, metadata = extract_pdf(pdf_data)

    ocr_results = {}
    scanned_pages = [p.page_number for p in pages if p.is_scanned]
    if scanned_pages and os.environ.get("DOCUMENT_INTELLIGENCE_ENDPOINT"):
        from ocr_service import ocr_pdf_pages
        ocr_results = ocr_pdf_pages(pdf_data, scanned_pages)

    html_content, image_files = build_html(
        pages=pages,
        ocr_results=ocr_results,
        metadata=metadata,
        embed_images=False,
    )

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{pdf_name}.html", html_content.encode("utf-8"))
        for img_name, img_bytes in image_files.items():
            zf.writestr(f"images/{img_name}", img_bytes)

    zip_buffer.seek(0)
    return Response(
        zip_buffer.getvalue(),
        mimetype="application/zip",
        headers={"Content-Disposition": f"attachment; filename={pdf_name}.zip"},
    )


if __name__ == "__main__":
    port = 5000
    if "--port" in sys.argv:
        idx = sys.argv.index("--port")
        port = int(sys.argv[idx + 1])
    print(f"Starting PDF-to-HTML web UI on http://localhost:{port}")
    app.run(host="127.0.0.1", port=port, debug=True)
