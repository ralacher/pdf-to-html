# ⚠️ DEPRECATED — This file is the legacy Azure Functions entry point.
# It has been replaced by:
#   - app/main.py    (FastAPI HTTP endpoints)
#   - app/worker.py  (Queue-based conversion worker)
# Kept as reference and rollback fallback. Not deployed to Container Apps.

import io
import json
import logging
import os
import random
import time as time_module
import uuid
from datetime import datetime, timedelta, timezone

import azure.functions as func
from azure.core.exceptions import (
    ResourceNotFoundError,
    ServiceRequestError,
    ServiceResponseError,
    HttpResponseError,
)
from azure.storage.blob import (
    BlobSasPermissions,
    BlobServiceClient,
    ContentSettings,
    generate_blob_sas,
)
from azure.identity import DefaultAzureCredential

from backend.pdf_extractor import extract_pdf
from backend.ocr_service import ocr_pdf_pages
from backend.html_builder import build_html
from backend.models import (
    ALLOWED_EXTENSIONS,
    EXTENSION_CONTENT_TYPES,
    MAX_FILE_SIZE_BYTES,
    DocumentStatus,
)
from backend import status_service

app = func.FunctionApp()

logger = logging.getLogger(__name__)

# Output container for converted HTML and images
_OUTPUT_CONTAINER = os.environ.get("OUTPUT_CONTAINER", "converted")

# Input container for uploaded files
_INPUT_CONTAINER = "files"

# SAS token lifetime
_SAS_UPLOAD_EXPIRY_MINUTES = 15
_SAS_DOWNLOAD_EXPIRY_MINUTES = 60


def _get_blob_service_client() -> BlobServiceClient:
    """Create a BlobServiceClient supporting both connection-string and
    identity-based authentication.

    - **Local / Azurite:** Uses ``AzureWebJobsStorage`` connection string.
    - **Azure (managed identity):** Uses ``AzureWebJobsStorage__accountName``
      with ``DefaultAzureCredential``.
    """
    conn_str = os.environ.get("AzureWebJobsStorage", "")

    # Connection-string path (local dev / Azurite, or Azure with explicit
    # connection string).
    if conn_str and ("AccountKey=" in conn_str or "UseDevelopmentStorage=true" in conn_str):
        return BlobServiceClient.from_connection_string(conn_str)

    # Identity-based path (Azure managed identity).
    account_name = os.environ.get("AzureWebJobsStorage__accountName", "")
    if account_name:
        account_url = f"https://{account_name}.blob.core.windows.net"
        return BlobServiceClient(account_url, credential=DefaultAzureCredential())

    raise RuntimeError(
        "Storage not configured. Set AzureWebJobsStorage (connection string) "
        "or AzureWebJobsStorage__accountName (identity-based auth)."
    )


# ---------------------------------------------------------------------------
# T073: Blob storage retry with exponential backoff
# ---------------------------------------------------------------------------

def _retry_blob_operation(operation, max_retries: int = 3, initial_delay: float = 1.0):
    """Execute a blob operation with exponential backoff retry logic.
    
    Args:
        operation: A callable that performs the blob operation
        max_retries: Maximum number of retry attempts (default 3)
        initial_delay: Initial delay in seconds (default 1.0)
    
    Returns:
        The result of the operation
        
    Raises:
        The last exception if all retries fail
    """
    delay = initial_delay
    last_exception = None
    
    for attempt in range(max_retries):
        try:
            return operation()
        except (ServiceRequestError, ServiceResponseError, HttpResponseError) as e:
            last_exception = e
            if attempt < max_retries - 1:
                # Add jitter: random value between delay and delay*1.5
                jitter = delay * (1.0 + random.random() * 0.5)
                logger.warning(
                    "Blob operation failed (attempt %d/%d): %s. Retrying in %.2fs...",
                    attempt + 1,
                    max_retries,
                    str(e),
                    jitter,
                )
                time_module.sleep(jitter)
                delay *= 2  # Exponential backoff
            else:
                logger.error(
                    "Blob operation failed after %d attempts: %s",
                    max_retries,
                    str(e),
                )
    
    if last_exception:
        raise last_exception
    

def _is_password_protected_pdf(file_data: bytes) -> bool:
    """Check if a PDF is password-protected or encrypted.
    
    Args:
        file_data: Raw PDF file bytes
        
    Returns:
        True if the PDF is encrypted/password-protected
    """
    import pymupdf
    try:
        doc = pymupdf.open(stream=file_data, filetype="pdf")
        is_encrypted = doc.is_encrypted
        doc.close()
        return is_encrypted
    except Exception as e:
        # If we can't open the document at all, it might be encrypted
        error_msg = str(e).lower()
        if "password" in error_msg or "encrypt" in error_msg:
            return True
        raise


def _is_password_protected_docx(file_data: bytes) -> bool:
    """Check if a DOCX is password-protected or encrypted.
    
    Args:
        file_data: Raw DOCX file bytes
        
    Returns:
        True if the DOCX is encrypted/password-protected
    """
    from docx import Document
    try:
        Document(io.BytesIO(file_data))
        return False
    except Exception as e:
        error_msg = str(e).lower()
        if "password" in error_msg or "encrypt" in error_msg or "protected" in error_msg:
            return True
        # Check for specific python-docx encryption errors
        if "package" in error_msg and ("corrupt" in error_msg or "invalid" in error_msg):
            # Could be encryption, but we'll re-raise to not mask other errors
            pass
        raise


def _is_password_protected_pptx(file_data: bytes) -> bool:
    """Check if a PPTX is password-protected or encrypted.
    
    Args:
        file_data: Raw PPTX file bytes
        
    Returns:
        True if the PPTX is encrypted/password-protected
    """
    from pptx import Presentation
    try:
        Presentation(io.BytesIO(file_data))
        return False
    except Exception as e:
        error_msg = str(e).lower()
        if "password" in error_msg or "encrypt" in error_msg or "protected" in error_msg:
            return True
        # Check for specific python-pptx encryption errors
        if "package" in error_msg and ("corrupt" in error_msg or "invalid" in error_msg):
            # Could be encryption, but we'll re-raise to not mask other errors
            pass
        raise


@app.blob_trigger(arg_name="myblob", path="files/{name}",
                               connection="AzureWebJobsStorage")
def file_upload(myblob: func.InputStream):
    # Guard: skip the 0-byte placeholder blob created by generate_sas_token.
    # The real content arrives later when the browser PUTs via the SAS URL,
    # which triggers this function again with actual data.
    # NOTE: myblob.length can be None with Azurite, so we also read the
    # stream and check actual data length as a fallback.
    if myblob.length is not None and myblob.length == 0:
        logger.info("Skipping 0-byte placeholder blob: %s", myblob.name)
        return

    # Read file into memory early — also serves as a definitive 0-byte check
    # when myblob.length is None (Azurite edge case).
    file_data = myblob.read()
    if len(file_data) == 0:
        logger.info("Skipping 0-byte blob (length was None): %s", myblob.name)
        return

    blob_name = myblob.name or "unknown"
    logger.info("Processing file: %s (%d bytes)", blob_name, len(file_data))

    # Derive document_id from blob filename (format: <uuid>.<ext>)
    base_filename = blob_name.rsplit("/", 1)[-1]
    document_id = base_filename.rsplit(".", 1)[0] if "." in base_filename else base_filename

    # --- SAFETY NET: Reconstruct metadata if wiped by SAS upload ---
    # When the browser PUTs via SAS URL, it overwrites the placeholder blob
    # and ALL metadata is lost.  Detect this and re-set essential fields so
    # that _find_blob_by_id() and list_documents() can still locate the blob.
    blob_service = None
    try:
        blob_service = _get_blob_service_client()
        container = blob_service.get_container_client(_INPUT_CONTAINER)
        blob_client = container.get_blob_client(base_filename)
        props = blob_client.get_blob_properties()
        existing_meta = dict(props.metadata or {})

        if "document_id" not in existing_meta or "status" not in existing_meta or "name" not in existing_meta:
            ext_for_meta = ("." + base_filename.rsplit(".", 1)[-1].lower()) if "." in base_filename else ""
            logger.warning("Metadata missing/incomplete for %s — reconstructing from blob name", blob_name)
            reconstructed = {
                "document_id": document_id,
                "format": ALLOWED_EXTENSIONS.get(ext_for_meta, "pdf").value if ext_for_meta in ALLOWED_EXTENSIONS else "pdf",
                "name": existing_meta.get("name") or existing_meta.get("original_filename", "").rsplit(".", 1)[0] or document_id,
                "status": DocumentStatus.PROCESSING.value,
                "size_bytes": str(len(file_data)),
                "upload_timestamp": existing_meta.get("upload_timestamp") or datetime.now(timezone.utc).isoformat(),
                "pages_processed": "0",
                "has_review_flags": "False",
                "blob_path": f"{_INPUT_CONTAINER}/{base_filename}",
                "output_path": "",
                "review_pages": "[]",
                "processing_time_ms": "",
                "is_compliant": "",
                "error_message": "",
                "page_count": "",
                "original_filename": existing_meta.get("original_filename") or base_filename,
            }
            blob_client.set_blob_metadata(reconstructed)
    except Exception:
        logger.exception("Could not verify/restore metadata for %s", blob_name)

    # --- Set status to "processing" ---
    import time
    start_time = time.monotonic()

    try:
        if blob_service is None:
            blob_service = _get_blob_service_client()
        status_service.set_status(blob_service, document_id, "processing")
    except Exception:
        logger.warning("Could not set processing status for %s", document_id)
        blob_service = None

    try:
        # file_data already read at the top of the function (0-byte guard)

        # --- T071: Check for password-protected documents ---
        ext = ("." + base_filename.rsplit(".", 1)[-1].lower()) if "." in base_filename else ""
        
        try:
            if ext == ".pdf":
                if _is_password_protected_pdf(file_data):
                    raise ValueError("PASSWORD_PROTECTED")
            elif ext == ".docx":
                if _is_password_protected_docx(file_data):
                    raise ValueError("PASSWORD_PROTECTED")
            elif ext == ".pptx":
                if _is_password_protected_pptx(file_data):
                    raise ValueError("PASSWORD_PROTECTED")
        except ValueError as ve:
            if "PASSWORD_PROTECTED" in str(ve):
                error_msg = "This document is password-protected. Please remove the password and re-upload."
                logger.warning("Password-protected document rejected: %s", blob_name)
                if blob_service is None:
                    blob_service = _get_blob_service_client()
                status_service.set_status(
                    blob_service,
                    document_id,
                    "failed",
                    error_message=error_msg,
                )
                return
            raise

        # --- Step 1: Extract content (route by file extension) ---
        if ext == ".docx":
            from backend.docx_extractor import extract_docx
            pages, metadata = extract_docx(file_data)
        elif ext == ".pptx":
            from backend.pptx_extractor import extract_pptx
            pages, metadata = extract_pptx(file_data)
        else:
            pages, metadata = extract_pdf(file_data)
        logger.info("Extracted %d pages. Metadata: %s", len(pages), metadata.get("title", "N/A"))

        # --- Step 2: Identify scanned pages that need OCR ---
        scanned_pages = [p.page_number for p in pages if p.is_scanned]
        ocr_results = {}

        if scanned_pages and ext not in (".docx", ".pptx"):
            logger.info("Sending %d scanned page(s) to Document Intelligence for OCR", len(scanned_pages))
            try:
                ocr_results = ocr_pdf_pages(pdf_data=file_data, page_numbers=scanned_pages)
                logger.info("OCR complete for %d page(s)", len(ocr_results))
            except Exception:
                logger.exception("Document Intelligence OCR failed — scanned pages will have no text")

        # --- Step 3: Build accessible HTML ---
        html_content, image_files = build_html(
            pages=pages,
            ocr_results=ocr_results,
            metadata=metadata,
            embed_images=False,  # Store images as separate blobs
        )

        # --- Step 3b: Run WCAG validation on generated HTML ---
        from backend.wcag_validator import validate_html as wcag_validate
        wcag_violations = wcag_validate(html_content)
        is_compliant = not any(
            v.severity in ("critical", "serious") for v in wcag_violations
        )
        if wcag_violations:
            logger.warning(
                "WCAG validation found %d violation(s) (compliant=%s)",
                len(wcag_violations),
                is_compliant,
            )

        # --- Step 3c: Collect OCR review flags ---
        review_pages: list[int] = []
        for page_num, ocr_page in ocr_results.items():
            if ocr_page.needs_review:
                review_pages.append(page_num + 1)  # 1-based for user-facing
        review_pages.sort()
        has_review_flags = len(review_pages) > 0

        # --- Step 4: Upload results to blob storage ---
        if blob_service is None:
            blob_service = _get_blob_service_client()
        container_client = blob_service.get_container_client(_OUTPUT_CONTAINER)

        # Ensure output container exists (with retry)
        def _create_container():
            try:
                container_client.create_container()
            except Exception:
                pass  # Container already exists
        
        _retry_blob_operation(_create_container)

        # Derive output path from input blob name
        # e.g. "files/report.pdf" -> "report"
        base_name = blob_name.rsplit("/", 1)[-1]
        for known_ext in (".pdf", ".docx", ".pptx"):
            if base_name.lower().endswith(known_ext):
                base_name = base_name[:-len(known_ext)]
                break

        # Upload HTML (with retry)
        html_blob_name = f"{base_name}/{base_name}.html"
        
        def _upload_html():
            container_client.upload_blob(
                name=html_blob_name,
                data=html_content.encode("utf-8"),
                overwrite=True,
                content_settings=ContentSettings(content_type="text/html; charset=utf-8"),
            )
        
        _retry_blob_operation(_upload_html)
        logger.info("Uploaded HTML: %s/%s", _OUTPUT_CONTAINER, html_blob_name)

        # Upload extracted images (with retry for each)
        for img_filename, img_bytes in image_files.items():
            img_blob_name = f"{base_name}/images/{img_filename}"
            ext = img_filename.rsplit(".", 1)[-1].lower()
            mime = {"png": "image/png", "jpeg": "image/jpeg", "jpg": "image/jpeg"}.get(ext, "application/octet-stream")
            
            def _upload_image():
                container_client.upload_blob(
                    name=img_blob_name,
                    data=img_bytes,
                    overwrite=True,
                    content_settings=ContentSettings(content_type=mime),
                )
            
            _retry_blob_operation(_upload_image)

        # --- Step 5: Set status to "completed" with metadata ---
        elapsed_ms = int((time.monotonic() - start_time) * 1000)

        try:
            status_service.set_status(
                blob_service,
                document_id,
                "completed",
                page_count=str(len(pages)),
                pages_processed=str(len(pages)),
                processing_time_ms=str(elapsed_ms),
                is_compliant=str(is_compliant),
                has_review_flags=str(has_review_flags),
                review_pages=str(review_pages),
                output_path=f"{_OUTPUT_CONTAINER}/{html_blob_name}",
            )
        except Exception:
            logger.exception("Could not update completed status for %s", document_id)

        logger.info(
            "Done. Uploaded %d image(s) for '%s' in %dms (compliant=%s, review_pages=%s)",
            len(image_files),
            blob_name,
            elapsed_ms,
            is_compliant,
            review_pages,
        )

    except Exception:
        # --- On error: set status to "failed" ---
        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        logger.exception("Conversion failed for %s", blob_name)
        try:
            if blob_service is None:
                blob_service = _get_blob_service_client()
            status_service.set_status(
                blob_service,
                document_id,
                "failed",
                error_message=f"Conversion failed after {elapsed_ms}ms",
                processing_time_ms=str(elapsed_ms),
            )
        except Exception:
            logger.exception("Could not set failed status for %s", document_id)


# ---------------------------------------------------------------------------
# T017: SAS token generation for browser-direct uploads
# ---------------------------------------------------------------------------

@app.route(route="upload/sas-token", methods=["POST"],
           auth_level=func.AuthLevel.ANONYMOUS)
def generate_sas_token(req: func.HttpRequest) -> func.HttpResponse:
    """Generate a short-lived SAS token for direct browser-to-blob upload.

    Accepts JSON body: { filename, content_type, size_bytes }
    Returns JSON: { document_id, upload_url, expires_at }
    """
    # --- Parse & validate request body ------------------------------------
    try:
        body = req.get_json()
    except ValueError:
        return _json_error("Invalid JSON body", 400)

    filename = body.get("filename", "")
    content_type = body.get("content_type", "")
    size_bytes = body.get("size_bytes", 0)

    if not filename or not isinstance(filename, str):
        return _json_error("filename is required", 400)

    # Validate extension
    ext = _file_extension(filename)
    if ext not in ALLOWED_EXTENSIONS:
        return _json_error(
            "Unsupported format. Accepted: .pdf, .docx, .pptx", 400
        )

    # Validate content type matches extension
    expected_ct = EXTENSION_CONTENT_TYPES.get(ext, "")
    if content_type != expected_ct:
        return _json_error(
            f"content_type must be '{expected_ct}' for {ext} files", 400
        )

    # Validate size
    if not isinstance(size_bytes, int) or size_bytes <= 0:
        return _json_error("size_bytes must be a positive integer", 400)
    if size_bytes > MAX_FILE_SIZE_BYTES:
        return _json_error("File exceeds 100MB limit", 400)

    # --- Generate document ID & SAS token ---------------------------------
    try:
        blob_service = _get_blob_service_client()
        document_id = str(uuid.uuid4())
        doc_format = ALLOWED_EXTENSIONS[ext].value
        doc_name = filename.rsplit(".", 1)[0] if "." in filename else filename
        blob_name = f"{document_id}{ext}"

        # Ensure the input container exists (with retry)
        container_client = blob_service.get_container_client(_INPUT_CONTAINER)
        
        def _create_input_container():
            try:
                container_client.create_container()
            except Exception:
                pass  # already exists
        
        _retry_blob_operation(_create_input_container)

        # T074: Handle filename conflicts by checking if blob exists
        # Since we're using document_id (UUID) as the blob name, conflicts are
        # virtually impossible. But we store the original filename in metadata
        # for display purposes and ensure uniqueness at the document_id level.
        
        # Pre-create the blob with initial metadata so status tracking works
        # even before the upload completes.  Upload an empty placeholder;
        # the real content arrives via the SAS URL.
        initial_metadata = {
            "document_id": document_id,
            "name": doc_name,
            "original_filename": filename,  # T074: preserve for display
            "format": doc_format,
            "size_bytes": str(size_bytes),
            "upload_timestamp": datetime.now(timezone.utc).isoformat(),
            "status": DocumentStatus.PENDING.value,
            "error_message": "",
            "page_count": "",
            "pages_processed": "0",
            "has_review_flags": "False",
            "blob_path": f"{_INPUT_CONTAINER}/{blob_name}",
            "output_path": "",
            "review_pages": "[]",
            "processing_time_ms": "",
            "is_compliant": "",
        }

        # Create blob placeholder (will be overwritten by browser upload) - with retry
        blob_client = container_client.get_blob_client(blob_name)
        
        def _create_placeholder():
            blob_client.upload_blob(b"", overwrite=True, metadata=initial_metadata)
        
        _retry_blob_operation(_create_placeholder)

        # Generate SAS token
        expiry = datetime.now(timezone.utc) + timedelta(
            minutes=_SAS_UPLOAD_EXPIRY_MINUTES
        )
        account_name = blob_service.account_name

        sas_token = _generate_sas_token_str(
            blob_service,
            _INPUT_CONTAINER,
            blob_name,
            BlobSasPermissions(write=True, create=True),
            expiry,
        )

        if _is_local_storage():
            upload_url = f"http://127.0.0.1:10000/{account_name}/{_INPUT_CONTAINER}/{blob_name}?{sas_token}"
        else:
            upload_url = f"https://{account_name}.blob.core.windows.net/{_INPUT_CONTAINER}/{blob_name}?{sas_token}"

        return func.HttpResponse(
            json.dumps({
                "document_id": document_id,
                "upload_url": upload_url,
                "expires_at": expiry.isoformat(),
                "metadata": initial_metadata,
            }),
            status_code=200,
            mimetype="application/json",
        )

    except Exception:
        logger.exception("Failed to generate SAS token")
        return _json_error("Storage service unavailable. Please retry.", 500)


# ---------------------------------------------------------------------------
# T018: Document status query
# ---------------------------------------------------------------------------

@app.route(route="documents/status", methods=["GET"],
           auth_level=func.AuthLevel.ANONYMOUS)
def get_document_status(req: func.HttpRequest) -> func.HttpResponse:
    """Return processing status for a single document or all documents.

    Query params:
        document_id (optional): Return status for a single document.

    Returns JSON matching the status API contract.
    """
    try:
        blob_service = _get_blob_service_client()
        document_id = req.params.get("document_id")

        if document_id:
            doc = status_service.get_status(blob_service, document_id)
            if doc is None:
                return _json_error("Document not found", 404)
            return func.HttpResponse(
                json.dumps(doc.to_dict(), default=str),
                status_code=200,
                mimetype="application/json",
            )

        # List all documents with batch summary (single blob scan)
        documents = status_service.list_documents(blob_service)
        batch_summary = status_service.get_batch_summary(
            blob_service, documents=documents
        )

        return func.HttpResponse(
            json.dumps(
                {
                    "documents": [d.to_dict() for d in documents],
                    "summary": batch_summary,
                    "batch_summary": batch_summary,
                },
                default=str,
            ),
            status_code=200,
            mimetype="application/json",
        )

    except Exception:
        logger.exception("Failed to query document status")
        return _json_error("Failed to retrieve document status", 500)


# ---------------------------------------------------------------------------
# T019: Download URL generation
# ---------------------------------------------------------------------------

@app.route(route="documents/{document_id}/download", methods=["GET"],
           auth_level=func.AuthLevel.ANONYMOUS)
def get_download_url(req: func.HttpRequest) -> func.HttpResponse:
    """Generate time-limited download URLs for a completed conversion.

    Path param: document_id
    Returns JSON with html_url, preview_url, assets, zip_url, etc.
    """
    document_id = req.route_params.get("document_id", "")
    if not document_id:
        return _json_error("document_id is required", 400)

    try:
        blob_service = _get_blob_service_client()
        doc = status_service.get_status(blob_service, document_id)

        if doc is None:
            return _json_error("Document not found", 404)

        if doc.status == DocumentStatus.PROCESSING.value:
            return func.HttpResponse(
                json.dumps({
                    "error": "Document is still processing",
                    "status": "processing",
                }),
                status_code=409,
                mimetype="application/json",
            )

        if doc.status == DocumentStatus.PENDING.value:
            return func.HttpResponse(
                json.dumps({
                    "error": "Document is still processing",
                    "status": "pending",
                }),
                status_code=409,
                mimetype="application/json",
            )

        if doc.status == DocumentStatus.FAILED.value:
            return _json_error(
                f"Document conversion failed: {doc.error_message or 'unknown error'}",
                404,
            )

        # --- Document is completed — build download URLs ------------------
        account_name = blob_service.account_name
        expiry = datetime.now(timezone.utc) + timedelta(
            minutes=_SAS_DOWNLOAD_EXPIRY_MINUTES
        )

        base_name = doc.name
        html_blob = f"{base_name}/{base_name}.html"
        zip_blob = f"{base_name}/{base_name}.zip"

        html_url = _generate_download_sas_url(
            blob_service, _OUTPUT_CONTAINER, html_blob, expiry
        )
        preview_url = html_url  # Same URL — contract specifies this

        # Discover image assets in the output container
        container_client = blob_service.get_container_client(_OUTPUT_CONTAINER)
        assets: list[dict] = []
        images_prefix = f"{base_name}/images/"
        try:
            for blob in container_client.list_blobs(name_starts_with=images_prefix):
                asset_url = _generate_download_sas_url(
                    blob_service, _OUTPUT_CONTAINER, blob.name, expiry
                )
                assets.append({
                    "filename": blob.name.split("/")[-1],
                    "url": asset_url,
                    "size_bytes": blob.size or 0,
                })
        except Exception:
            logger.warning("Could not enumerate image assets for %s", document_id)

        # Zip URL (may not exist yet; URL is still valid per contract)
        zip_url = _generate_download_sas_url(
            blob_service, _OUTPUT_CONTAINER, zip_blob, expiry
        )

        # Build image_urls list (just the SAS URLs, no metadata)
        image_urls = [asset["url"] for asset in assets] if assets else []

        return func.HttpResponse(
            json.dumps({
                "document_id": document_id,
                "name": doc.name,
                "html_url": html_url,
                "preview_url": preview_url,
                "assets": assets,
                "zip_url": zip_url,
                "wcag_compliant": doc.is_compliant if doc.is_compliant is not None else True,
                "review_pages": doc.review_pages,
                "expires_at": expiry.isoformat(),
                # Frontend-compatible aliases (downloadService.ts expects these)
                "download_url": html_url,
                "filename": doc.name,
                "image_urls": image_urls if image_urls else None,
            }),
            status_code=200,
            mimetype="application/json",
        )

    except Exception:
        logger.exception("Failed to generate download URLs for %s", document_id)
        return _json_error("Failed to generate download URLs", 500)


# ---------------------------------------------------------------------------
# T003: Delete a single document
# ---------------------------------------------------------------------------

@app.route(route="documents/{document_id}", methods=["DELETE"],
           auth_level=func.AuthLevel.ANONYMOUS)
def delete_document(req: func.HttpRequest) -> func.HttpResponse:
    """Delete a single document and all its conversion output.

    Path param: document_id
    Returns 200 on success, 404 if not found, 409 if currently processing.
    """
    document_id = req.route_params.get("document_id", "")
    if not document_id:
        return _json_error("document_id is required", 400)

    try:
        blob_service = _get_blob_service_client()

        # Guard: refuse to delete a document that is still processing
        doc = status_service.get_status(blob_service, document_id)
        if doc is None:
            return _json_error("Document not found", 404)
        if doc.status == DocumentStatus.PROCESSING.value:
            return func.HttpResponse(
                json.dumps({
                    "error": "Cannot delete a document while it is being processed",
                    "status": "processing",
                }),
                status_code=409,
                mimetype="application/json",
            )

        # Perform deletion (with retry for transient blob failures)
        result = _retry_blob_operation(
            lambda: status_service.delete_document(
                blob_service, document_id, _OUTPUT_CONTAINER
            )
        )

        logger.info("Document %s deleted (%d blobs removed)",
                     document_id, result["blobs_removed"])

        return func.HttpResponse(
            json.dumps({
                "message": "Document deleted",
                "document_id": document_id,
                "blobs_removed": result["blobs_removed"],
            }),
            status_code=200,
            mimetype="application/json",
        )

    except ResourceNotFoundError:
        return _json_error("Document not found", 404)
    except Exception:
        logger.exception("Failed to delete document %s", document_id)
        return _json_error("Failed to delete document", 500)


# ---------------------------------------------------------------------------
# T004: Delete all documents
# ---------------------------------------------------------------------------

@app.route(route="documents", methods=["DELETE"],
           auth_level=func.AuthLevel.ANONYMOUS)
def delete_all_documents(req: func.HttpRequest) -> func.HttpResponse:
    """Delete all documents from input and output storage.

    Returns 200 with deletion counts, 500 on error.
    """
    try:
        blob_service = _get_blob_service_client()
        result = status_service.delete_all_documents(
            blob_service, _OUTPUT_CONTAINER
        )

        logger.info(
            "All documents deleted: %d input, %d output",
            result["deleted_input"],
            result["deleted_output"],
        )

        return func.HttpResponse(
            json.dumps({
                "message": "All documents deleted",
                "deleted_input": result["deleted_input"],
                "deleted_output": result["deleted_output"],
            }),
            status_code=200,
            mimetype="application/json",
        )

    except Exception:
        logger.exception("Failed to delete all documents")
        return _json_error("Failed to delete all documents", 500)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _json_error(message: str, status_code: int) -> func.HttpResponse:
    """Return a JSON error response."""
    return func.HttpResponse(
        json.dumps({"error": message}),
        status_code=status_code,
        mimetype="application/json",
    )


def _file_extension(filename: str) -> str:
    """Extract the lowercase file extension including the dot."""
    if "." not in filename:
        return ""
    return "." + filename.rsplit(".", 1)[-1].lower()


def _is_azurite(connection_string: str) -> bool:
    """Return True when the connection string targets the Azurite emulator."""
    return (
        "UseDevelopmentStorage=true" in connection_string
        or "127.0.0.1:10000" in connection_string
    )


def _is_local_storage() -> bool:
    """Return True when the app is configured for Azurite local storage."""
    conn_str = os.environ.get("AzureWebJobsStorage", "")
    return _is_azurite(conn_str)


def _uses_identity_auth() -> bool:
    """Return True when the app uses identity-based storage auth (no key)."""
    conn_str = os.environ.get("AzureWebJobsStorage", "")
    if conn_str and ("AccountKey=" in conn_str or "UseDevelopmentStorage=true" in conn_str):
        return False
    return bool(os.environ.get("AzureWebJobsStorage__accountName", ""))


# Well-known Azurite storage credentials
_AZURITE_ACCOUNT_NAME = "devstoreaccount1"
_AZURITE_ACCOUNT_KEY = (
    "Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq"
    "/K1SZFPTOtr/KBHBeksoGMGw=="
)


def _extract_account_key(connection_string: str) -> str | None:
    """Parse AccountKey from an Azure Storage connection string.

    When the connection string is the Azurite shorthand
    ``UseDevelopmentStorage=true``, returns the well-known Azurite
    account key (there is no explicit AccountKey in that string).

    Returns ``None`` if no account key is available (identity-based auth).
    """
    if _is_azurite(connection_string):
        return _AZURITE_ACCOUNT_KEY
    for part in connection_string.split(";"):
        part = part.strip()
        if part.lower().startswith("accountkey="):
            return part.split("=", 1)[1]
    return None


def _generate_sas_token_str(
    blob_service: BlobServiceClient,
    container: str,
    blob_name: str,
    permission: BlobSasPermissions,
    expiry: datetime,
) -> str:
    """Generate a SAS token string using account key or user delegation key.

    - **Local / Azurite:** Uses account key from connection string.
    - **Azure (managed identity):** Requests a ``UserDelegationKey`` from the
      blob service and generates a user-delegation SAS.
    """
    account_name = blob_service.account_name
    conn_str = os.environ.get("AzureWebJobsStorage", "")
    account_key = _extract_account_key(conn_str) if conn_str else None

    if account_key:
        # Account-key SAS (local / Azurite / connection-string deployments)
        return generate_blob_sas(
            account_name=account_name,
            container_name=container,
            blob_name=blob_name,
            account_key=account_key,
            permission=permission,
            expiry=expiry,
        )

    # User-delegation SAS (identity-based auth on Azure)
    start_time = datetime.now(timezone.utc) - timedelta(minutes=5)
    delegation_key = blob_service.get_user_delegation_key(start_time, expiry)
    return generate_blob_sas(
        account_name=account_name,
        container_name=container,
        blob_name=blob_name,
        user_delegation_key=delegation_key,
        permission=permission,
        expiry=expiry,
    )


def _generate_download_sas_url(
    blob_service: BlobServiceClient,
    container: str,
    blob_name: str,
    expiry: datetime,
) -> str:
    """Generate a read-only SAS URL for downloading a blob."""
    account_name = blob_service.account_name
    sas_token = _generate_sas_token_str(
        blob_service, container, blob_name,
        BlobSasPermissions(read=True), expiry,
    )
    if _is_local_storage():
        return f"http://127.0.0.1:10000/{account_name}/{container}/{blob_name}?{sas_token}"
    return f"https://{account_name}.blob.core.windows.net/{container}/{blob_name}?{sas_token}"
