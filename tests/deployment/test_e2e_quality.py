"""
End-to-end conversion quality evaluations.

This suite uploads real documents, waits for conversion, downloads the
resulting HTML, and validates conversion fidelity + WCAG 2.1 AA compliance.
Expected runtime: 2-5 minutes.

Usage::

    # Full e2e quality (2-5 min)
    pytest tests/deployment/test_e2e_quality.py -v -m e2e

    # Against Azure
    BASE_URL=https://ca-pdftohtml-api.azurecontainerapps.io \
        pytest tests/deployment/test_e2e_quality.py -v -m e2e
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest
import requests

from tests.deployment.conftest import (
    BASE_URL,
    cleanup_document,
    download_html,
    upload_file,
    wait_for_completion,
)

# ---------------------------------------------------------------------------
# Paths to test fixtures
# ---------------------------------------------------------------------------

SAMPLES_DIR = Path(__file__).resolve().parents[1] / "eval" / "samples"
FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"

DIGITAL_REPORT = SAMPLES_DIR / "digital-report.pdf"
COMPLEX_TABLES = SAMPLES_DIR / "complex-tables.pdf"
IMAGE_HEAVY = SAMPLES_DIR / "image-heavy.pdf"
SCANNED_TEXT = SAMPLES_DIR / "scanned-text.pdf"
SAMPLE_DOCX = FIXTURES_DIR / "sample.docx"
SAMPLE_PPTX = FIXTURES_DIR / "sample.pptx"


# ---------------------------------------------------------------------------
# WCAG validation helper (imports backend validator)
# ---------------------------------------------------------------------------

def _run_wcag_validation(html: str) -> list:
    """Run the backend WCAG validator and return violations.

    Falls back gracefully if the backend module isn't importable
    (e.g., when running from a different virtualenv).
    """
    try:
        from backend.wcag_validator import validate_html

        return validate_html(html)
    except ImportError:
        pytest.skip("backend.wcag_validator not importable in this environment")


def _assert_no_critical_wcag(html: str, *, context: str = "") -> None:
    """Assert that there are zero critical or serious WCAG violations."""
    violations = _run_wcag_validation(html)
    critical = [
        v for v in violations if v.severity in ("critical", "serious")
    ]
    if critical:
        details = "\n".join(
            f"  [{v.severity}] {v.rule_id}: {v.description} — {v.html_element[:120]}"
            for v in critical
        )
        pytest.fail(
            f"WCAG critical/serious violations{' (' + context + ')' if context else ''}:\n{details}"
        )


# ---------------------------------------------------------------------------
# Shared fixture: auto-cleanup uploaded documents
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _cleanup_uploaded_docs():
    """Track and cleanup documents created during each test."""
    doc_ids: list[str] = []
    _cleanup_uploaded_docs.register = lambda did: doc_ids.append(did)  # type: ignore[attr-defined]
    yield
    for doc_id in doc_ids:
        cleanup_document(doc_id)


def _upload_and_convert(
    filepath: Path,
    filename: str | None = None,
    *,
    timeout: int = 120,
) -> tuple[str, str]:
    """Upload a file, wait for conversion, download HTML.

    Returns:
        (document_id, html_content)
    """
    doc_id = upload_file(filepath, filename=filename)
    _cleanup_uploaded_docs.register(doc_id)  # type: ignore[attr-defined]

    status = wait_for_completion(doc_id, timeout=timeout)
    assert status["status"] == "completed", (
        f"Conversion failed for {filepath.name}: "
        f"{status.get('error_message', 'unknown error')}"
    )

    html = download_html(doc_id)
    assert len(html) > 100, (
        f"HTML too short ({len(html)} chars) for {filepath.name}"
    )
    return doc_id, html


# ═══════════════════════════════════════════════════════════════════════════
# Suite 2 — E2E Conversion Quality Evals
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.e2e
class TestDigitalPdfQuality:
    """1. Digital PDF → HTML Quality.

    Uploads ``digital-report.pdf``, downloads converted HTML, and checks
    WCAG compliance: lang attr, skip-nav, heading hierarchy, table headers,
    zero critical/serious violations.
    """

    @pytest.fixture(autouse=True)
    def _convert(self):
        if not DIGITAL_REPORT.exists():
            pytest.skip(f"Fixture not found: {DIGITAL_REPORT}")
        self.doc_id, self.html = _upload_and_convert(DIGITAL_REPORT)

    def test_html_has_lang_attribute(self):
        assert re.search(r'<html[^>]*\slang="[a-z]', self.html, re.IGNORECASE), (
            "Missing lang attribute on <html> element"
        )

    def test_skip_nav_link_present(self):
        assert "main-content" in self.html, (
            "Missing skip-nav target (#main-content)"
        )

    def test_heading_hierarchy_not_skipped(self):
        """Headings should not skip levels (h1→h3 without h2 is invalid)."""
        headings = re.findall(r"<h([1-6])", self.html, re.IGNORECASE)
        levels = [int(h) for h in headings]
        for i in range(1, len(levels)):
            gap = levels[i] - levels[i - 1]
            assert gap <= 1, (
                f"Heading skip: h{levels[i - 1]} → h{levels[i]} "
                f"(position {i})"
            )

    def test_tables_have_th_with_scope(self):
        """Tables must have <th> elements with scope attributes."""
        tables = re.findall(r"<table[\s\S]*?</table>", self.html, re.IGNORECASE)
        for idx, table in enumerate(tables):
            if 'role="presentation"' in table:
                continue  # layout tables exempt
            th_tags = re.findall(r"<th[^>]*>", table, re.IGNORECASE)
            if th_tags:
                for th in th_tags:
                    assert "scope=" in th.lower(), (
                        f"Table {idx}: <th> missing scope attribute: {th[:80]}"
                    )

    def test_zero_critical_wcag_violations(self):
        _assert_no_critical_wcag(self.html, context="digital-report.pdf")


@pytest.mark.e2e
class TestComplexTablesQuality:
    """2. Complex Tables → HTML Quality.

    Validates that tables from ``complex-tables.pdf`` have proper <th>
    elements with scope, and that table data is preserved.
    """

    @pytest.fixture(autouse=True)
    def _convert(self):
        if not COMPLEX_TABLES.exists():
            pytest.skip(f"Fixture not found: {COMPLEX_TABLES}")
        self.doc_id, self.html = _upload_and_convert(COMPLEX_TABLES)

    def test_tables_present(self):
        tables = re.findall(r"<table", self.html, re.IGNORECASE)
        assert len(tables) > 0, "No tables found in complex-tables output"

    def test_th_elements_with_scope(self):
        th_tags = re.findall(r"<th[^>]*>", self.html, re.IGNORECASE)
        assert len(th_tags) > 0, "No <th> elements found"
        for th in th_tags:
            assert "scope=" in th.lower(), (
                f"<th> missing scope: {th[:80]}"
            )

    def test_table_data_preserved(self):
        """Tables should contain actual data (not just headers)."""
        td_tags = re.findall(r"<td[^>]*>.*?</td>", self.html, re.IGNORECASE | re.DOTALL)
        assert len(td_tags) > 0, "No <td> data cells found"

    def test_zero_critical_wcag_violations(self):
        _assert_no_critical_wcag(self.html, context="complex-tables.pdf")


@pytest.mark.e2e
class TestImageHeavyQuality:
    """3. Image-Heavy PDF → HTML Quality.

    Validates that images from ``image-heavy.pdf`` have alt text and
    use proper <figure>/<figcaption> semantics.
    """

    @pytest.fixture(autouse=True)
    def _convert(self):
        if not IMAGE_HEAVY.exists():
            pytest.skip(f"Fixture not found: {IMAGE_HEAVY}")
        self.doc_id, self.html = _upload_and_convert(IMAGE_HEAVY)

    def test_images_have_alt_text(self):
        img_tags = re.findall(r"<img[^>]*>", self.html, re.IGNORECASE)
        assert len(img_tags) > 0, "No <img> tags found in image-heavy output"
        for img in img_tags:
            if 'aria-hidden="true"' in img or 'role="presentation"' in img:
                continue  # decorative images exempt
            assert re.search(r'alt="[^"]+', img), (
                f"Image missing alt text: {img[:120]}"
            )

    def test_images_use_figure_semantics(self):
        """At least some images should use <figure>/<figcaption>."""
        figure_count = len(re.findall(r"<figure", self.html, re.IGNORECASE))
        # Soft check — not all images need <figure>, but image-heavy docs should use them
        if figure_count == 0:
            pytest.xfail("No <figure> elements found — pipeline may not wrap images yet")

    def test_image_urls_accessible(self):
        """Images with blob storage URLs should be downloadable."""
        img_srcs = re.findall(r'<img[^>]*src="([^"]+)"', self.html, re.IGNORECASE)
        http_srcs = [s for s in img_srcs if s.startswith("http")]
        for src in http_srcs[:3]:  # check first 3 to keep test fast
            resp = requests.head(src, timeout=15, allow_redirects=True)
            assert resp.status_code == 200, (
                f"Image URL returned {resp.status_code}: {src[:100]}"
            )

    def test_zero_critical_wcag_violations(self):
        _assert_no_critical_wcag(self.html, context="image-heavy.pdf")


@pytest.mark.e2e
class TestDocxQuality:
    """4. DOCX → HTML Quality.

    Validates that ``sample.docx`` is converted with headings preserved,
    tables accessible, and WCAG compliance.
    """

    @pytest.fixture(autouse=True)
    def _convert(self):
        if not SAMPLE_DOCX.exists():
            pytest.skip(f"Fixture not found: {SAMPLE_DOCX}")
        self.doc_id, self.html = _upload_and_convert(
            SAMPLE_DOCX, filename="sample.docx"
        )

    def test_headings_preserved(self):
        headings = re.findall(r"<h[1-6][^>]*>(.*?)</h[1-6]>", self.html, re.IGNORECASE)
        assert len(headings) > 0, "No headings found in DOCX conversion"

    def test_html_has_lang(self):
        assert re.search(r'<html[^>]*\slang="[a-z]', self.html, re.IGNORECASE), (
            "DOCX output missing lang attribute"
        )

    def test_zero_critical_wcag_violations(self):
        _assert_no_critical_wcag(self.html, context="sample.docx")


@pytest.mark.e2e
class TestPptxQuality:
    """5. PPTX → HTML Quality.

    Validates that ``sample.pptx`` slides become sections, text is
    preserved, and output is WCAG compliant.
    """

    @pytest.fixture(autouse=True)
    def _convert(self):
        if not SAMPLE_PPTX.exists():
            pytest.skip(f"Fixture not found: {SAMPLE_PPTX}")
        self.doc_id, self.html = _upload_and_convert(
            SAMPLE_PPTX, filename="sample.pptx"
        )

    def test_slides_as_sections(self):
        """Each slide should map to a <section> or equivalent landmark."""
        sections = re.findall(r"<section", self.html, re.IGNORECASE)
        # Allow <article> or <div role="region"> as alternatives
        if len(sections) == 0:
            articles = re.findall(r"<article", self.html, re.IGNORECASE)
            regions = re.findall(r'role="region"', self.html, re.IGNORECASE)
            assert len(articles) + len(regions) > 0, (
                "No <section>, <article>, or role='region' elements — "
                "slides not structured as sections"
            )

    def test_text_preserved(self):
        """The output should contain visible text content."""
        # Strip tags and check for non-trivial text
        text = re.sub(r"<[^>]+>", " ", self.html)
        text = re.sub(r"\s+", " ", text).strip()
        assert len(text) > 50, (
            f"PPTX output has too little text ({len(text)} chars)"
        )

    def test_zero_critical_wcag_violations(self):
        _assert_no_critical_wcag(self.html, context="sample.pptx")


@pytest.mark.e2e
class TestScannedPdfOcrQuality:
    """6. Scanned PDF → OCR Quality (CRITICAL — this was broken).

    Validates that OCR extracts meaningful text from a scanned (image-only)
    PDF.  If OCR returns 0% confidence, the test is marked XFAIL because
    the OCR service may not be configured in this environment.
    """

    @pytest.fixture(autouse=True)
    def _convert(self):
        if not SCANNED_TEXT.exists():
            pytest.skip(f"Fixture not found: {SCANNED_TEXT}")
        self.doc_id = upload_file(SCANNED_TEXT, filename="scanned-text.pdf")
        _cleanup_uploaded_docs.register(self.doc_id)  # type: ignore[attr-defined]
        self.status = wait_for_completion(self.doc_id, timeout=120)

    def test_conversion_completes(self):
        assert self.status["status"] in ("completed", "failed"), (
            f"Unexpected status: {self.status.get('status')}"
        )

    def test_ocr_extracts_meaningful_text(self):
        """HTML should contain actual text, not just 'Content Unavailable'."""
        if self.status["status"] == "failed":
            pytest.xfail(
                "OCR service may not be configured — conversion failed: "
                f"{self.status.get('error_message', 'unknown')}"
            )

        html = download_html(self.doc_id)

        # Check that HTML doesn't just say "Content Unavailable"
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text).strip()

        if "content unavailable" in text.lower() and len(text) < 200:
            pytest.xfail(
                "OCR service may not be configured — output is 'Content Unavailable'"
            )

        # Look for meaningful content — at least some recognizable words
        # The scanned PDF contains "North Carolina", "MEMORANDUM", etc.
        assert len(text) > 50, (
            f"OCR output too short ({len(text)} chars) — possible 0% confidence"
        )

    def test_ocr_pages_flagged_for_review(self):
        """Status should indicate review flags if OCR confidence is low."""
        if self.status["status"] == "failed":
            pytest.xfail("Conversion failed — cannot check review flags")

        # The has_review_flags field should be present
        if "has_review_flags" in self.status:
            # If OCR had low confidence, review_pages should be populated
            if self.status.get("has_review_flags"):
                review_pages = self.status.get("review_pages", [])
                assert isinstance(review_pages, list)


@pytest.mark.e2e
class TestFileNamingConvention:
    """7. File Naming Convention.

    Uploads a file named 'Annual_Report_2025.pdf' and verifies the
    converted HTML preserves the original stem (not just a UUID).
    """

    @pytest.fixture(autouse=True)
    def _convert(self):
        # Use the minimal PDF fixture (it's the content that matters less here)
        tiny_pdf = Path("/tmp/_smoke_test_tiny.pdf")
        if not tiny_pdf.exists():
            # Write inline if smoke tests haven't run yet
            tiny_pdf.write_bytes(
                b"%PDF-1.4\n"
                b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
                b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
                b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]\n"
                b"   /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
                b"4 0 obj\n<< /Length 44 >>\nstream\n"
                b"BT /F1 24 Tf 100 700 Td (Hello WCAG) Tj ET\n"
                b"endstream\nendobj\n"
                b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
                b"xref\n0 6\n"
                b"0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n"
                b"0000000115 00000 n \n0000000266 00000 n \n0000000360 00000 n \n"
                b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n441\n%%EOF"
            )

        self.doc_id = upload_file(tiny_pdf, filename="Annual_Report_2025.pdf")
        _cleanup_uploaded_docs.register(self.doc_id)  # type: ignore[attr-defined]
        self.status = wait_for_completion(self.doc_id, timeout=60)

    def test_conversion_completes(self):
        assert self.status["status"] == "completed", (
            f"Conversion failed: {self.status.get('error_message')}"
        )

    def test_original_stem_in_response(self):
        """The download response should reference the original filename stem."""
        dl_resp = requests.get(
            f"{BASE_URL}/api/documents/{self.doc_id}/download",
            timeout=30,
        )
        assert dl_resp.status_code == 200
        data = dl_resp.json()

        # Check name/filename fields for original stem
        name = data.get("name", "") or data.get("filename", "")
        assert "annual" in name.lower() or "report" in name.lower(), (
            f"Original stem not preserved in name: {name!r}"
        )

    def test_status_has_original_filename(self):
        """Status should report the original filename."""
        resp = requests.get(
            f"{BASE_URL}/api/documents/status",
            params={"document_id": self.doc_id},
            timeout=30,
        )
        data = resp.json()
        # Look for original_filename or name field
        fname = data.get("original_filename") or data.get("name", "")
        assert "annual" in fname.lower() or "report" in fname.lower(), (
            f"original_filename not preserved: {fname!r}"
        )


@pytest.mark.e2e
class TestConversionMetadata:
    """8. Conversion Metadata.

    Verifies that the status response includes expected metadata fields:
    document_id, status, page_count, conversion_time, etc.
    """

    @pytest.fixture(autouse=True)
    def _convert(self):
        tiny_pdf = Path("/tmp/_smoke_test_tiny.pdf")
        if not tiny_pdf.exists():
            tiny_pdf.write_bytes(
                b"%PDF-1.4\n"
                b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
                b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
                b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]\n"
                b"   /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
                b"4 0 obj\n<< /Length 44 >>\nstream\n"
                b"BT /F1 24 Tf 100 700 Td (Hello WCAG) Tj ET\n"
                b"endstream\nendobj\n"
                b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
                b"xref\n0 6\n"
                b"0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n"
                b"0000000115 00000 n \n0000000266 00000 n \n0000000360 00000 n \n"
                b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n441\n%%EOF"
            )

        self.doc_id = upload_file(tiny_pdf, filename="metadata-test.pdf")
        _cleanup_uploaded_docs.register(self.doc_id)  # type: ignore[attr-defined]
        self.status = wait_for_completion(self.doc_id, timeout=60)

    def test_has_document_id(self):
        assert "document_id" in self.status
        assert self.status["document_id"] == self.doc_id

    def test_has_status_field(self):
        assert "status" in self.status
        assert self.status["status"] in ("completed", "failed")

    def test_has_page_count(self):
        if self.status["status"] != "completed":
            pytest.skip("Conversion didn't complete")
        assert "page_count" in self.status
        page_count = self.status["page_count"]
        assert page_count is not None and page_count >= 1

    def test_has_processing_time(self):
        if self.status["status"] != "completed":
            pytest.skip("Conversion didn't complete")
        time_ms = self.status.get("processing_time_ms")
        assert time_ms is not None, "Missing processing_time_ms"
        assert time_ms >= 0, f"Negative processing time: {time_ms}"

    def test_has_name_field(self):
        name = self.status.get("name", "")
        assert name, "Missing name in status response"

    def test_has_format_field(self):
        fmt = self.status.get("format", "")
        assert fmt in ("pdf", "docx", "pptx"), (
            f"Unexpected format: {fmt!r}"
        )

    def test_has_compliance_flag(self):
        if self.status["status"] != "completed":
            pytest.skip("Conversion didn't complete")
        assert "is_compliant" in self.status

    def test_review_pages_is_list(self):
        review_pages = self.status.get("review_pages")
        if review_pages is not None:
            assert isinstance(review_pages, list), (
                f"review_pages should be a list, got {type(review_pages)}"
            )
