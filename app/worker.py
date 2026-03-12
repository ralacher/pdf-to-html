"""
Queue-based conversion worker for the WCAG document-to-HTML converter.

Polls the ``conversion-jobs`` Azure Storage Queue for messages enqueued by
Event Grid (production) or the ``/api/upload/sas-token`` endpoint (local
dev with Azurite).  Each message triggers the full conversion pipeline:

    download → detect format → extract → OCR → build HTML → WCAG validate → upload

The worker runs as a long-lived process alongside (or instead of) the
FastAPI server when ``WORKER_MODE=true``.

Graceful shutdown on SIGTERM / SIGINT.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone

from azure.storage.blob import ContentSettings

from app.config import settings
from app.dependencies import (
    get_blob_service_client,
    get_queue_client,
    retry_blob_operation,
)
from app.security import check_password_protection
from backend import status_service
from backend.models import ALLOWED_EXTENSIONS, DocumentStatus

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_POLL_INTERVAL_SECONDS = 2
_MAX_DEQUEUE_COUNT = 3  # T019: poison queue threshold


# ---------------------------------------------------------------------------
# Worker loop
# ---------------------------------------------------------------------------

class ConversionWorker:
    """Polls the conversion-jobs queue and processes uploaded documents."""

    def __init__(self) -> None:
        self._running = False

    # -- Lifecycle ----------------------------------------------------------

    def start(self) -> None:
        """Start the poll loop.  Blocks until shutdown signal received."""
        self._running = True
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

        logger.info(
            "Worker started — polling queue '%s' every %ds",
            settings.QUEUE_NAME,
            _POLL_INTERVAL_SECONDS,
        )

        while self._running:
            try:
                self._poll_once()
            except Exception:
                logger.exception("Unexpected error in worker poll loop")
            time.sleep(_POLL_INTERVAL_SECONDS)

        logger.info("Worker stopped gracefully.")

    def stop(self) -> None:
        """Request graceful shutdown."""
        logger.info("Shutdown requested — finishing current work…")
        self._running = False

    def _handle_signal(self, signum: int, _frame) -> None:  # noqa: ANN001
        logger.info("Received signal %s — shutting down", signal.Signals(signum).name)
        self.stop()

    # -- Queue polling ------------------------------------------------------

    def _poll_once(self) -> None:
        """Receive and process a batch of queue messages."""
        queue_client = get_queue_client()

        messages = queue_client.receive_messages(
            messages_per_page=1,
            visibility_timeout=300,  # 5 min — enough for large conversions
        )

        for message in messages:
            # T019: Poison queue handling — skip messages that have failed
            # too many times.
            if message.dequeue_count >= _MAX_DEQUEUE_COUNT:
                logger.error(
                    "Poison message detected (dequeue_count=%d, id=%s). "
                    "Deleting to prevent infinite retries.",
                    message.dequeue_count,
                    message.id,
                )
                queue_client.delete_message(message)
                continue

            try:
                self._process_message(message, queue_client)
            except Exception:
                logger.exception(
                    "Failed to process queue message id=%s (attempt %d/%d)",
                    message.id,
                    message.dequeue_count,
                    _MAX_DEQUEUE_COUNT,
                )
                # Do NOT delete — message becomes visible again after timeout
                # and will be retried (up to _MAX_DEQUEUE_COUNT).

    # -- Message processing -------------------------------------------------

    def _process_message(self, message, queue_client) -> None:  # noqa: ANN001
        """Parse an Event Grid envelope and run the conversion pipeline."""
        # Decode the message body (base64-encoded JSON)
        raw = message.content
        try:
            decoded = base64.b64decode(raw).decode("utf-8")
        except Exception:
            # Might not be base64; try raw
            decoded = raw if isinstance(raw, str) else raw.decode("utf-8")

        envelope = json.loads(decoded)

        # Extract blob name from the Event Grid subject field
        # Subject format: /blobServices/default/containers/files/blobs/<blob_name>
        subject = envelope.get("subject", "")
        blob_name = subject.rsplit("/blobs/", 1)[-1] if "/blobs/" in subject else ""

        if not blob_name:
            logger.warning(
                "Could not extract blob_name from message subject: %s", subject
            )
            queue_client.delete_message(message)
            return

        logger.info("Processing conversion job for blob: %s", blob_name)

        # Run the conversion pipeline
        self._convert(blob_name)

        # Success — delete the message so it isn't retried
        queue_client.delete_message(message)
        logger.info("Conversion complete for %s — message deleted", blob_name)

    # -- Conversion pipeline ------------------------------------------------

    def _convert(self, blob_name: str) -> None:
        """Download, convert, and upload a single document."""
        blob_service = get_blob_service_client()
        container_client = blob_service.get_container_client(
            settings.INPUT_CONTAINER
        )
        blob_client = container_client.get_blob_client(blob_name)

        # Derive document_id from blob filename (format: <uuid>.<ext>)
        base_filename = blob_name.rsplit("/", 1)[-1]
        document_id = (
            base_filename.rsplit(".", 1)[0]
            if "." in base_filename
            else base_filename
        )

        # --- Wait for real content (SAS upload may still be in flight) ----
        file_data = self._wait_for_content(blob_client, blob_name)
        if file_data is None:
            logger.info(
                "Blob %s still 0 bytes after waiting — skipping", blob_name
            )
            return

        logger.info("Processing file: %s (%d bytes)", blob_name, len(file_data))

        # --- Reconstruct metadata if wiped by SAS upload ------------------
        try:
            props = blob_client.get_blob_properties()
            existing_meta = dict(props.metadata or {})

            if (
                "document_id" not in existing_meta
                or "status" not in existing_meta
                or "name" not in existing_meta
            ):
                ext_for_meta = (
                    ("." + base_filename.rsplit(".", 1)[-1].lower())
                    if "." in base_filename
                    else ""
                )
                logger.warning(
                    "Metadata missing/incomplete for %s — reconstructing",
                    blob_name,
                )
                reconstructed = {
                    "document_id": document_id,
                    "format": (
                        ALLOWED_EXTENSIONS.get(ext_for_meta, "pdf").value
                        if ext_for_meta in ALLOWED_EXTENSIONS
                        else "pdf"
                    ),
                    "name": (
                        existing_meta.get("name")
                        or existing_meta.get("original_filename", "")
                        .rsplit(".", 1)[0]
                        or document_id
                    ),
                    "status": DocumentStatus.PROCESSING.value,
                    "size_bytes": str(len(file_data)),
                    "upload_timestamp": (
                        existing_meta.get("upload_timestamp")
                        or datetime.now(timezone.utc).isoformat()
                    ),
                    "pages_processed": "0",
                    "has_review_flags": "False",
                    "blob_path": f"{settings.INPUT_CONTAINER}/{base_filename}",
                    "output_path": "",
                    "review_pages": "[]",
                    "processing_time_ms": "",
                    "is_compliant": "",
                    "error_message": "",
                    "page_count": "",
                    "original_filename": (
                        existing_meta.get("original_filename") or base_filename
                    ),
                }
                blob_client.set_blob_metadata(reconstructed)
        except Exception:
            logger.exception(
                "Could not verify/restore metadata for %s", blob_name
            )

        # --- Set status to "processing" -----------------------------------
        start_time = time.monotonic()

        try:
            status_service.set_status(blob_service, document_id, "processing")
        except Exception:
            logger.warning(
                "Could not set processing status for %s", document_id
            )

        try:
            # --- T020: Check for password-protected documents -------------
            ext = (
                ("." + base_filename.rsplit(".", 1)[-1].lower())
                if "." in base_filename
                else ""
            )

            try:
                if check_password_protection(file_data, ext):
                    error_msg = (
                        "This document is password-protected. "
                        "Please remove the password and re-upload."
                    )
                    logger.warning(
                        "Password-protected document rejected: %s", blob_name
                    )
                    status_service.set_status(
                        blob_service,
                        document_id,
                        "failed",
                        error_message=error_msg,
                    )
                    return
            except ValueError:
                pass  # Unsupported extension for password check — continue

            # --- Step 1: Extract content (route by file extension) --------
            if ext == ".docx":
                from backend.docx_extractor import extract_docx

                pages, metadata = extract_docx(file_data)
            elif ext == ".pptx":
                from backend.pptx_extractor import extract_pptx

                pages, metadata = extract_pptx(file_data)
            else:
                from backend.pdf_extractor import extract_pdf

                pages, metadata = extract_pdf(file_data)

            logger.info(
                "Extracted %d pages. Metadata: %s",
                len(pages),
                metadata.get("title", "N/A"),
            )

            # --- Step 2: Identify scanned pages that need OCR -------------
            scanned_pages = [p.page_number for p in pages if p.is_scanned]
            ocr_results: dict = {}

            if scanned_pages and ext not in (".docx", ".pptx"):
                logger.info(
                    "Sending %d scanned page(s) to Document Intelligence",
                    len(scanned_pages),
                )
                try:
                    from backend.ocr_service import ocr_pdf_pages

                    ocr_results = ocr_pdf_pages(
                        pdf_data=file_data, page_numbers=scanned_pages
                    )
                    logger.info(
                        "OCR complete for %d page(s)", len(ocr_results)
                    )
                except Exception:
                    logger.exception(
                        "Document Intelligence OCR failed — "
                        "scanned pages will have no text"
                    )

            # --- Step 3: Build accessible HTML ----------------------------
            from backend.html_builder import build_html

            html_content, image_files = build_html(
                pages=pages,
                ocr_results=ocr_results,
                metadata=metadata,
                embed_images=False,  # Store images as separate blobs
            )

            # --- Step 3b: Run WCAG validation on generated HTML -----------
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

            # --- Step 3c: Collect OCR review flags ------------------------
            review_pages: list[int] = []
            for page_num, ocr_page in ocr_results.items():
                if ocr_page.needs_review:
                    review_pages.append(page_num + 1)  # 1-based for users
            review_pages.sort()
            has_review_flags = len(review_pages) > 0

            # --- Step 4: Upload results to blob storage -------------------
            output_client = blob_service.get_container_client(
                settings.OUTPUT_CONTAINER
            )

            # Ensure output container exists (with retry)
            def _create_container():
                try:
                    output_client.create_container()
                except Exception:
                    pass  # Container already exists

            retry_blob_operation(_create_container)

            # Derive output path from blob name
            output_base = base_filename
            for known_ext in (".pdf", ".docx", ".pptx"):
                if output_base.lower().endswith(known_ext):
                    output_base = output_base[: -len(known_ext)]
                    break

            # Upload HTML (with retry)
            html_blob_name = f"{output_base}/{output_base}.html"

            def _upload_html():
                output_client.upload_blob(
                    name=html_blob_name,
                    data=html_content.encode("utf-8"),
                    overwrite=True,
                    content_settings=ContentSettings(
                        content_type="text/html; charset=utf-8"
                    ),
                )

            retry_blob_operation(_upload_html)
            logger.info(
                "Uploaded HTML: %s/%s",
                settings.OUTPUT_CONTAINER,
                html_blob_name,
            )

            # Upload extracted images (with retry for each)
            for img_filename, img_bytes in image_files.items():
                img_blob_name = f"{output_base}/images/{img_filename}"
                img_ext = img_filename.rsplit(".", 1)[-1].lower()
                mime = {
                    "png": "image/png",
                    "jpeg": "image/jpeg",
                    "jpg": "image/jpeg",
                }.get(img_ext, "application/octet-stream")

                def _upload_image(
                    _name=img_blob_name, _data=img_bytes, _mime=mime
                ):
                    output_client.upload_blob(
                        name=_name,
                        data=_data,
                        overwrite=True,
                        content_settings=ContentSettings(content_type=_mime),
                    )

                retry_blob_operation(_upload_image)

            # --- Step 5: Set status to "completed" with metadata ----------
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
                    output_path=f"{settings.OUTPUT_CONTAINER}/{html_blob_name}",
                )
            except Exception:
                logger.exception(
                    "Could not update completed status for %s", document_id
                )

            logger.info(
                "Done. Uploaded %d image(s) for '%s' in %dms "
                "(compliant=%s, review_pages=%s)",
                len(image_files),
                blob_name,
                elapsed_ms,
                is_compliant,
                review_pages,
            )

        except Exception:
            # --- On error: set status to "failed" -------------------------
            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            logger.exception("Conversion failed for %s", blob_name)
            try:
                status_service.set_status(
                    blob_service,
                    document_id,
                    "failed",
                    error_message=f"Conversion failed after {elapsed_ms}ms",
                    processing_time_ms=str(elapsed_ms),
                )
            except Exception:
                logger.exception(
                    "Could not set failed status for %s", document_id
                )

    # -- Helpers ------------------------------------------------------------

    @staticmethod
    def _wait_for_content(
        blob_client,
        blob_name: str,
        max_wait: float = 30.0,
        poll: float = 2.0,
    ) -> bytes | None:
        """Wait for the blob to have non-zero content.

        The SAS upload endpoint creates a 0-byte placeholder; the real
        content arrives shortly after when the browser PUTs via the SAS URL.
        """
        deadline = time.monotonic() + max_wait

        while time.monotonic() < deadline:
            try:
                data = blob_client.download_blob().readall()
                if len(data) > 0:
                    return data
            except Exception:
                pass
            time.sleep(poll)

        return None


# ---------------------------------------------------------------------------
# Entry-point (``python -m app.worker``)
# ---------------------------------------------------------------------------

def main() -> None:
    """Start the conversion worker."""
    log_level = os.environ.get("LOG_LEVEL", "INFO")
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    handler.setFormatter(formatter)
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO), handlers=[handler]
    )
    worker = ConversionWorker()
    worker.start()


if __name__ == "__main__":
    main()
