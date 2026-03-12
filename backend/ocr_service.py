"""
Azure Document Intelligence integration for OCR on scanned PDF pages.
Uses the prebuilt-layout model to extract text, tables, and reading order.
"""

import logging
import os
from dataclasses import dataclass, field

from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import (
    AnalyzeDocumentRequest,
    DocumentAnalysisFeature,
    AnalyzeResult,
)
from azure.identity import DefaultAzureCredential

logger = logging.getLogger(__name__)

# Pages with average OCR confidence below this threshold are flagged for review
_CONFIDENCE_THRESHOLD = 0.70


@dataclass
class OcrSpan:
    """A text span extracted via OCR."""
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    confidence: float


@dataclass
class OcrTableCell:
    """A single cell in a detected table."""
    row_index: int
    column_index: int
    text: str
    is_header: bool = False
    row_span: int = 1
    column_span: int = 1


@dataclass
class OcrTable:
    """A table detected on a page."""
    row_count: int
    column_count: int
    cells: list[OcrTableCell] = field(default_factory=list)


@dataclass
class OcrPageResult:
    """OCR results for a single page."""
    page_number: int  # 0-based to match PageResult
    width: float
    height: float
    lines: list[OcrSpan] = field(default_factory=list)
    tables: list[OcrTable] = field(default_factory=list)
    confidence: float = 1.0  # average OCR confidence for the page (0.0–1.0)
    needs_review: bool = False  # True when confidence < threshold


def _get_client() -> DocumentIntelligenceClient:
    """Create a Document Intelligence client.

    Uses API key (DOCUMENT_INTELLIGENCE_KEY) if set, otherwise falls back
    to Entra ID via DefaultAzureCredential.
    """
    endpoint = os.environ["DOCUMENT_INTELLIGENCE_ENDPOINT"]
    key = os.environ.get("DOCUMENT_INTELLIGENCE_KEY")
    if key:
        from azure.core.credentials import AzureKeyCredential
        return DocumentIntelligenceClient(
            endpoint=endpoint,
            credential=AzureKeyCredential(key),
        )
    return DocumentIntelligenceClient(
        endpoint=endpoint,
        credential=DefaultAzureCredential(),
    )


def _polygon_to_bbox(polygon: list[float]) -> tuple[float, float, float, float]:
    """Convert a polygon [x1,y1,x2,y2,...] to (x0, y0, x1, y1) bounding box."""
    xs = polygon[0::2]
    ys = polygon[1::2]
    return min(xs), min(ys), max(xs), max(ys)


def _calculate_page_confidence(di_page, line_spans: list[OcrSpan]) -> float:
    """Calculate average OCR confidence for a page from word-level scores.

    Uses Document Intelligence's word-level confidence when available,
    falling back to line-level span confidences.
    """
    word_confidences: list[float] = []

    # Primary source: word-level confidence from Document Intelligence
    if hasattr(di_page, "words") and di_page.words:
        for word in di_page.words:
            if hasattr(word, "confidence") and word.confidence is not None:
                word_confidences.append(word.confidence)

    if word_confidences:
        return sum(word_confidences) / len(word_confidences)

    # Fallback: use line-level span confidences
    if line_spans:
        return sum(s.confidence for s in line_spans) / len(line_spans)

    return 0.0


def ocr_pdf_pages(pdf_data: bytes, page_numbers: list[int]) -> dict[int, OcrPageResult]:
    """
    Run OCR on specific pages of a PDF using Azure Document Intelligence.

    Args:
        pdf_data: The full PDF file bytes.
        page_numbers: 0-based page numbers that need OCR.

    Returns:
        Dict mapping 0-based page number to OcrPageResult.

    Per-page OCR confidence is calculated from word-level confidence scores
    and pages with confidence below 0.70 are flagged with needs_review=True.
    If OCR fails for a specific page, a partial result with confidence=0
    and needs_review=True is returned so processing can continue.
    """
    if not page_numbers:
        return {}

    client = _get_client()

    # Document Intelligence uses 1-based page numbers
    di_pages = ",".join(str(p + 1) for p in page_numbers)

    try:
        poller = client.begin_analyze_document(
            "prebuilt-layout",
            AnalyzeDocumentRequest(bytes_source=pdf_data),
            pages=di_pages,
            features=[DocumentAnalysisFeature.QUERY_FIELDS],
        )
        result: AnalyzeResult = poller.result()
    except Exception:
        # T036: If the entire OCR call fails, return empty results with
        # confidence=0 for every requested page so the pipeline continues.
        logger.exception("Document Intelligence OCR failed for all pages")
        results: dict[int, OcrPageResult] = {}
        for pn in page_numbers:
            results[pn] = OcrPageResult(
                page_number=pn,
                width=0,
                height=0,
                confidence=0.0,
                needs_review=True,
            )
        return results

    results: dict[int, OcrPageResult] = {}

    # Process pages
    if result.pages:
        for di_page in result.pages:
            page_num = di_page.page_number - 1  # convert to 0-based
            if page_num not in page_numbers:
                continue

            try:
                ocr_page = OcrPageResult(
                    page_number=page_num,
                    width=di_page.width or 0,
                    height=di_page.height or 0,
                )

                # Extract lines with positions and word-level confidence
                if di_page.lines:
                    for line in di_page.lines:
                        if line.polygon and line.content:
                            x0, y0, x1, y1 = _polygon_to_bbox(line.polygon)

                            # Use word-level confidence average for the line
                            # when available; fall back to 1.0
                            line_confidence = 1.0
                            if hasattr(di_page, "words") and di_page.words:
                                # Find words that belong to this line by text matching
                                line_word_confs = []
                                for word in di_page.words:
                                    if (hasattr(word, "confidence")
                                            and word.confidence is not None
                                            and word.content
                                            and word.content in line.content):
                                        line_word_confs.append(word.confidence)
                                if line_word_confs:
                                    line_confidence = sum(line_word_confs) / len(line_word_confs)

                            ocr_page.lines.append(OcrSpan(
                                text=line.content,
                                x0=x0, y0=y0, x1=x1, y1=y1,
                                confidence=line_confidence,
                            ))

                # Calculate page-level confidence and review flag
                page_conf = _calculate_page_confidence(di_page, ocr_page.lines)
                ocr_page.confidence = round(page_conf, 4)
                ocr_page.needs_review = page_conf < _CONFIDENCE_THRESHOLD

                if ocr_page.needs_review:
                    logger.warning(
                        "Page %d OCR confidence %.1f%% < %.0f%% — flagging for review",
                        page_num + 1,
                        page_conf * 100,
                        _CONFIDENCE_THRESHOLD * 100,
                    )

                results[page_num] = ocr_page

            except Exception:
                # T036: Per-page failure — log and continue with a stub result
                logger.exception(
                    "OCR processing failed for page %d — returning empty result",
                    page_num + 1,
                )
                results[page_num] = OcrPageResult(
                    page_number=page_num,
                    width=di_page.width or 0,
                    height=di_page.height or 0,
                    confidence=0.0,
                    needs_review=True,
                )

    # Ensure pages that were requested but not returned by DI still get entries
    for pn in page_numbers:
        if pn not in results:
            logger.warning(
                "Page %d was requested for OCR but not returned by Document Intelligence",
                pn + 1,
            )
            results[pn] = OcrPageResult(
                page_number=pn,
                width=0,
                height=0,
                confidence=0.0,
                needs_review=True,
            )

    # Process tables and assign to pages
    if result.tables:
        for table in result.tables:
            if not table.bounding_regions:
                continue
            table_page = table.bounding_regions[0].page_number - 1
            if table_page not in results:
                continue

            ocr_table = OcrTable(
                row_count=table.row_count,
                column_count=table.column_count,
            )
            if table.cells:
                for cell in table.cells:
                    ocr_table.cells.append(OcrTableCell(
                        row_index=cell.row_index,
                        column_index=cell.column_index,
                        text=cell.content or "",
                        is_header=(cell.kind == "columnHeader") if cell.kind else False,
                        row_span=cell.row_span or 1,
                        column_span=cell.column_span or 1,
                    ))
            results[table_page].tables.append(ocr_table)

    return results
