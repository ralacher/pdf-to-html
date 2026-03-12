"""
FastAPI application for the WCAG-compliant document-to-HTML converter.

This module creates the ``app`` instance, configures CORS, and exposes:

* ``/health`` and ``/ready`` probes (Azure Container Apps)
* ``POST /api/upload/sas-token`` — browser-direct SAS upload
* ``GET  /api/documents/status`` — document status query
* ``GET  /api/documents/{document_id}/download`` — download URLs
* ``DELETE /api/documents/{document_id}`` — single document deletion
* ``DELETE /api/documents`` — bulk document deletion
"""

from __future__ import annotations

import base64
import json
import logging
import os
import sys
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from azure.core.exceptions import ResourceNotFoundError
from azure.storage.blob import BlobSasPermissions
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.dependencies import (
    SAS_DOWNLOAD_EXPIRY_MINUTES,
    SAS_UPLOAD_EXPIRY_MINUTES,
    generate_download_sas_url,
    generate_sas_token_str,
    get_blob_service_client,
    get_queue_client,
    is_local_storage,
    retry_blob_operation,
)
from backend import status_service
from backend.models import (
    ALLOWED_EXTENSIONS,
    EXTENSION_CONTENT_TYPES,
    MAX_FILE_SIZE_BYTES,
    DocumentStatus,
)


# ---------------------------------------------------------------------------
# Structured logging
# ---------------------------------------------------------------------------

def configure_logging() -> None:
    """Set up structured logging with consistent formatting."""
    log_level = os.environ.get("LOG_LEVEL", "INFO")
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    handler.setFormatter(formatter)
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO), handlers=[handler]
    )


configure_logging()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan — ensure storage containers & queue exist (idempotent)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Create blob containers and queue on startup if they don't exist.

    This is especially important for local development with Azurite where the
    emulator starts with a clean slate.  Failures are non-fatal — the
    containers may already exist in production.
    """
    try:
        blob_service = get_blob_service_client()
        for container_name in [settings.INPUT_CONTAINER, settings.OUTPUT_CONTAINER]:
            try:
                blob_service.get_container_client(container_name).create_container()
                logger.info("Created container: %s", container_name)
            except Exception:
                pass  # Already exists — totally fine

        # Create the conversion-jobs queue
        try:
            get_queue_client().create_queue()
            logger.info("Created queue: %s", settings.QUEUE_NAME)
        except Exception:
            pass  # Already exists
    except Exception:
        logger.warning(
            "Could not initialise storage during startup — "
            "containers / queue may need to be created manually."
        )
    yield


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

app = FastAPI(
    title="PDF-to-HTML WCAG Converter",
    version="1.0.0",
    description="Converts PDF, DOCX and PPTX documents to WCAG 2.1 AA compliant HTML.",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS — explicit origins required for allow_credentials=True (F6/F15)
# Override via comma-separated ALLOWED_ORIGINS env var per environment.
# ---------------------------------------------------------------------------
_default_origins = [
    "https://ca-pdftohtml-frontend.blackplant-e84b1473.eastus.azurecontainerapps.io",
    "http://localhost:3000",
]
_env_origins = os.environ.get("ALLOWED_ORIGINS", "")
_allowed_origins: list[str] = (
    [o.strip() for o in _env_origins.split(",") if o.strip()]
    if _env_origins
    else _default_origins
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _file_extension(filename: str) -> str:
    """Extract the lowercase file extension including the dot."""
    if "." not in filename:
        return ""
    return "." + filename.rsplit(".", 1)[-1].lower()


# ---------------------------------------------------------------------------
# Health & readiness probes
# ---------------------------------------------------------------------------

@app.get("/health")
async def health() -> dict:
    """Liveness probe — returns storage and queue connectivity status."""
    checks: dict[str, str] = {"storage": "ok", "queue": "ok"}

    try:
        blob_service = get_blob_service_client()
        blob_service.get_container_client(
            settings.INPUT_CONTAINER
        ).get_container_properties()
    except Exception:
        checks["storage"] = "error"

    try:
        get_queue_client().get_queue_properties()
    except Exception:
        checks["queue"] = "error"

    status = "healthy" if all(v == "ok" for v in checks.values()) else "degraded"
    return {"status": status, "version": "1.0.0", "checks": checks}


@app.get("/ready", response_model=None)
async def ready():
    """Readiness probe — returns 200 only when storage is reachable."""
    try:
        blob_service = get_blob_service_client()
        blob_service.get_container_client(
            settings.INPUT_CONTAINER
        ).get_container_properties()
        return {"status": "ready"}
    except Exception:
        return JSONResponse({"status": "not_ready"}, status_code=503)


# ---------------------------------------------------------------------------
# T010: POST /api/upload/sas-token — SAS token generation
# ---------------------------------------------------------------------------

@app.post("/api/upload/sas-token")
async def generate_sas_token(body: dict):
    """Generate a short-lived SAS token for direct browser-to-blob upload.

    Accepts JSON body: ``{filename, content_type, size_bytes}``
    Returns JSON: ``{document_id, upload_url, expires_at, metadata}``
    """
    # --- Parse & validate request body ------------------------------------
    filename = body.get("filename", "")
    content_type = body.get("content_type", "")
    size_bytes = body.get("size_bytes", 0)

    if not filename or not isinstance(filename, str):
        return JSONResponse({"error": "filename is required"}, status_code=400)

    # Validate extension
    ext = _file_extension(filename)
    if ext not in ALLOWED_EXTENSIONS:
        return JSONResponse(
            {"error": "Unsupported format. Accepted: .pdf, .docx, .pptx"},
            status_code=400,
        )

    # Validate content type matches extension
    expected_ct = EXTENSION_CONTENT_TYPES.get(ext, "")
    if content_type != expected_ct:
        return JSONResponse(
            {"error": f"content_type must be '{expected_ct}' for {ext} files"},
            status_code=400,
        )

    # Validate size
    if not isinstance(size_bytes, int) or size_bytes <= 0:
        return JSONResponse(
            {"error": "size_bytes must be a positive integer"}, status_code=400
        )
    if size_bytes > MAX_FILE_SIZE_BYTES:
        return JSONResponse({"error": "File exceeds 100MB limit"}, status_code=400)

    # --- Generate document ID & SAS token ---------------------------------
    try:
        blob_service = get_blob_service_client()
        document_id = str(uuid.uuid4())
        doc_format = ALLOWED_EXTENSIONS[ext].value
        doc_name = filename.rsplit(".", 1)[0] if "." in filename else filename
        blob_name = f"{document_id}{ext}"

        # Ensure the input container exists (with retry)
        container_client = blob_service.get_container_client(settings.INPUT_CONTAINER)

        def _create_input_container():
            try:
                container_client.create_container()
            except Exception:
                pass  # already exists

        retry_blob_operation(_create_input_container)

        # Pre-create the blob with initial metadata so status tracking works
        # even before the upload completes.  Upload an empty placeholder;
        # the real content arrives via the SAS URL.
        initial_metadata = {
            "document_id": document_id,
            "name": doc_name,
            "original_filename": filename,
            "format": doc_format,
            "size_bytes": str(size_bytes),
            "upload_timestamp": datetime.now(timezone.utc).isoformat(),
            "status": DocumentStatus.PENDING.value,
            "error_message": "",
            "page_count": "",
            "pages_processed": "0",
            "has_review_flags": "False",
            "blob_path": f"{settings.INPUT_CONTAINER}/{blob_name}",
            "output_path": "",
            "review_pages": "[]",
            "processing_time_ms": "",
            "is_compliant": "",
        }

        # Create blob placeholder (will be overwritten by browser upload)
        blob_client = container_client.get_blob_client(blob_name)

        def _create_placeholder():
            blob_client.upload_blob(b"", overwrite=True, metadata=initial_metadata)

        retry_blob_operation(_create_placeholder)

        # --- T021: Local dev queue simulation ---
        # When running locally (Azurite), Event Grid is not available.
        # Enqueue a simulated Event Grid message so the queue worker picks
        # it up after the browser uploads via the SAS URL.
        if is_local_storage():
            try:
                queue_client = get_queue_client()
                msg = json.dumps({
                    "subject": (
                        f"/blobServices/default/containers/"
                        f"{settings.INPUT_CONTAINER}/blobs/{blob_name}"
                    ),
                    "data": {
                        "contentType": content_type,
                        "contentLength": size_bytes,
                    },
                })
                # Queue messages must be base64 encoded for Azure Storage Queue
                encoded_msg = base64.b64encode(msg.encode("utf-8")).decode("utf-8")
                queue_client.send_message(encoded_msg)
                logger.info(
                    "Enqueued local conversion job for %s", blob_name
                )
            except Exception:
                logger.warning(
                    "Could not enqueue local conversion job for %s — "
                    "worker may not pick it up automatically",
                    blob_name,
                )

        # Generate SAS token
        expiry = datetime.now(timezone.utc) + timedelta(
            minutes=SAS_UPLOAD_EXPIRY_MINUTES
        )
        account_name = blob_service.account_name

        sas_token = generate_sas_token_str(
            blob_service,
            settings.INPUT_CONTAINER,
            blob_name,
            BlobSasPermissions(write=True, create=True),
            expiry,
        )

        if is_local_storage():
            upload_url = (
                f"http://127.0.0.1:10000/{account_name}/"
                f"{settings.INPUT_CONTAINER}/{blob_name}?{sas_token}"
            )
        else:
            upload_url = (
                f"https://{account_name}.blob.core.windows.net/"
                f"{settings.INPUT_CONTAINER}/{blob_name}?{sas_token}"
            )

        return {
            "document_id": document_id,
            "upload_url": upload_url,
            "expires_at": expiry.isoformat(),
            "metadata": initial_metadata,
        }

    except Exception:
        logger.exception("Failed to generate SAS token")
        return JSONResponse(
            {"error": "Storage service unavailable. Please retry."}, status_code=500
        )


# ---------------------------------------------------------------------------
# T011: GET /api/documents/status — Document status query
# ---------------------------------------------------------------------------

@app.get("/api/documents/status")
async def get_document_status(document_id: str | None = Query(default=None)):
    """Return processing status for a single document or all documents.

    Query params:
        document_id (optional): Return status for a single document.
    """
    try:
        blob_service = get_blob_service_client()

        if document_id:
            doc = status_service.get_status(blob_service, document_id)
            if doc is None:
                return JSONResponse({"error": "Document not found"}, status_code=404)
            return json.loads(json.dumps(doc.to_dict(), default=str))

        # List all documents with batch summary (single blob scan)
        documents = status_service.list_documents(blob_service)
        batch_summary = status_service.get_batch_summary(
            blob_service, documents=documents
        )

        return json.loads(
            json.dumps(
                {
                    "documents": [d.to_dict() for d in documents],
                    "summary": batch_summary,
                    "batch_summary": batch_summary,
                },
                default=str,
            )
        )

    except Exception:
        logger.exception("Failed to query document status")
        return JSONResponse(
            {"error": "Failed to retrieve document status"}, status_code=500
        )


# ---------------------------------------------------------------------------
# T012: GET /api/documents/{document_id}/download — Download URL generation
# ---------------------------------------------------------------------------

@app.get("/api/documents/{document_id}/download")
async def get_download_url(document_id: str):
    """Generate time-limited download URLs for a completed conversion.

    Path param: document_id
    Returns JSON with html_url, preview_url, assets, zip_url, etc.
    """
    if not document_id:
        return JSONResponse({"error": "document_id is required"}, status_code=400)

    try:
        blob_service = get_blob_service_client()
        doc = status_service.get_status(blob_service, document_id)

        if doc is None:
            return JSONResponse({"error": "Document not found"}, status_code=404)

        if doc.status == DocumentStatus.PROCESSING.value:
            return JSONResponse(
                {"error": "Document is still processing", "status": "processing"},
                status_code=409,
            )

        if doc.status == DocumentStatus.PENDING.value:
            return JSONResponse(
                {"error": "Document is still processing", "status": "pending"},
                status_code=409,
            )

        if doc.status == DocumentStatus.FAILED.value:
            return JSONResponse(
                {
                    "error": (
                        f"Document conversion failed: "
                        f"{doc.error_message or 'unknown error'}"
                    )
                },
                status_code=404,
            )

        # --- Document is completed — build download URLs ------------------
        expiry = datetime.now(timezone.utc) + timedelta(
            minutes=SAS_DOWNLOAD_EXPIRY_MINUTES
        )

        base_name = doc.name
        html_blob = f"{base_name}/{base_name}.html"
        zip_blob = f"{base_name}/{base_name}.zip"

        html_url = generate_download_sas_url(
            blob_service, settings.OUTPUT_CONTAINER, html_blob, expiry
        )
        preview_url = html_url  # Same URL — contract specifies this

        # Discover image assets in the output container
        container_client = blob_service.get_container_client(
            settings.OUTPUT_CONTAINER
        )
        assets: list[dict] = []
        images_prefix = f"{base_name}/images/"
        try:
            for blob in container_client.list_blobs(
                name_starts_with=images_prefix
            ):
                asset_url = generate_download_sas_url(
                    blob_service, settings.OUTPUT_CONTAINER, blob.name, expiry
                )
                assets.append(
                    {
                        "filename": blob.name.split("/")[-1],
                        "url": asset_url,
                        "size_bytes": blob.size or 0,
                    }
                )
        except Exception:
            logger.warning(
                "Could not enumerate image assets for %s", document_id
            )

        # Zip URL (may not exist yet; URL is still valid per contract)
        zip_url = generate_download_sas_url(
            blob_service, settings.OUTPUT_CONTAINER, zip_blob, expiry
        )

        # Build image_urls list (just the SAS URLs, no metadata)
        image_urls = [asset["url"] for asset in assets] if assets else []

        return {
            "document_id": document_id,
            "name": doc.name,
            "html_url": html_url,
            "preview_url": preview_url,
            "assets": assets,
            "zip_url": zip_url,
            "wcag_compliant": (
                doc.is_compliant if doc.is_compliant is not None else True
            ),
            "review_pages": doc.review_pages,
            "expires_at": expiry.isoformat(),
            # Frontend-compatible aliases (downloadService.ts expects these)
            "download_url": html_url,
            "filename": doc.name,
            "image_urls": image_urls if image_urls else None,
        }

    except Exception:
        logger.exception(
            "Failed to generate download URLs for %s", document_id
        )
        return JSONResponse(
            {"error": "Failed to generate download URLs"}, status_code=500
        )


# ---------------------------------------------------------------------------
# T013: DELETE /api/documents/{document_id} — Single document deletion
# ---------------------------------------------------------------------------

@app.delete("/api/documents/{document_id}")
async def delete_document(document_id: str):
    """Delete a single document and all its conversion output.

    Path param: document_id
    Returns 200 on success, 404 if not found, 409 if currently processing.
    """
    if not document_id:
        return JSONResponse(
            {"error": "document_id is required"}, status_code=400
        )

    try:
        blob_service = get_blob_service_client()

        # Guard: refuse to delete a document that is still processing
        doc = status_service.get_status(blob_service, document_id)
        if doc is None:
            return JSONResponse(
                {"error": "Document not found"}, status_code=404
            )
        if doc.status == DocumentStatus.PROCESSING.value:
            return JSONResponse(
                {
                    "error": "Cannot delete a document while it is being processed",
                    "status": "processing",
                },
                status_code=409,
            )

        # Perform deletion (with retry for transient blob failures)
        result = retry_blob_operation(
            lambda: status_service.delete_document(
                blob_service, document_id, settings.OUTPUT_CONTAINER
            )
        )

        logger.info(
            "Document %s deleted (%d blobs removed)",
            document_id,
            result["blobs_removed"],
        )

        return {
            "message": "Document deleted",
            "document_id": document_id,
            "blobs_removed": result["blobs_removed"],
        }

    except ResourceNotFoundError:
        return JSONResponse(
            {"error": "Document not found"}, status_code=404
        )
    except Exception:
        logger.exception("Failed to delete document %s", document_id)
        return JSONResponse(
            {"error": "Failed to delete document"}, status_code=500
        )


# ---------------------------------------------------------------------------
# T014: DELETE /api/documents — Bulk document deletion
# ---------------------------------------------------------------------------

@app.delete("/api/documents")
async def delete_all_documents():
    """Delete all documents from input and output storage.

    Returns 200 with deletion counts, 500 on error.
    """
    try:
        blob_service = get_blob_service_client()
        result = status_service.delete_all_documents(
            blob_service, settings.OUTPUT_CONTAINER
        )

        logger.info(
            "All documents deleted: %d input, %d output",
            result["deleted_input"],
            result["deleted_output"],
        )

        return {
            "message": "All documents deleted",
            "deleted_input": result["deleted_input"],
            "deleted_output": result["deleted_output"],
        }

    except Exception:
        logger.exception("Failed to delete all documents")
        return JSONResponse(
            {"error": "Failed to delete all documents"}, status_code=500
        )
