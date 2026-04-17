# -*- coding: utf-8 -*-
# SPDX-License-Identifier: Elastic-2.0
# Copyright (c) 2026 Mitch Kwiatkowski
# ARIS — Automated Regulatory Intelligence System
# Licensed under the Elastic License 2.0. See LICENSE in the project root.
"""
ARIS — PDF Agent

Three capabilities:

1. TEXT EXTRACTION
   Extracts clean text from any PDF file using pdfplumber (primary) with
   pypdf as fallback. Returns a normalised document dict identical to what
   API-based agents produce, so every downstream component (interpreter,
   diff agent, synthesis agent, learning agent) is unaware of the origin.

2. AUTO-DOWNLOAD
   Derives PDF URLs from existing documents already in the database:
     - Federal Register:  pdf_url field in raw_json (already fetched)
     - EUR-Lex:           deterministic URL from CELEX id — no API key needed
                          https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX:{id}
     - UK legislation:    deterministic URL from document id
                          https://www.legislation.gov.uk/.../pdfs/...
   Downloads the PDF, extracts text, and stores it as full_text on the
   existing document record. Records extraction metadata in pdf_metadata.

3. MANUAL INGEST (DROP FOLDER)
   Watches output/pdf_inbox/ for PDF files placed there manually.
   Each file is ingested with user-supplied metadata (jurisdiction, agency,
   doc_type, title, etc.). Supports any jurisdiction including those not
   covered by existing source agents — jurisdiction is free text.
   After ingestion the file is moved to output/pdfs/stored/ so the inbox
   stays clean.

All documents produced by this agent are tagged with origin="pdf_manual"
or origin="pdf_auto" and are otherwise indistinguishable from API-sourced
documents.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from config.settings import PDF_DROP_DIR, PDF_STORE_DIR, OUTPUT_DIR
from utils.cache import get_logger

log = get_logger("aris.pdf")

# ── PDF text extraction ───────────────────────────────────────────────────────


def extract_text_from_pdf(path: Path) -> Tuple[str, str, int]:
    """
    Extract text from a PDF file.

    Returns (text, method_used, page_count).

    Tries pdfplumber first (better layout preservation), falls back to
    pypdf if pdfplumber fails or returns very little text.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")

    text, method, pages = _extract_pdfplumber(path)

    # Fall back to pypdf if pdfplumber returned almost nothing
    if len(text.strip()) < 100:
        text_b, method_b, pages_b = _extract_pypdf(path)
        if len(text_b.strip()) > len(text.strip()):
            text, method, pages = text_b, method_b, pages_b

    text = _clean_extracted_text(text)
    log.info(
        "Extracted %d chars from %s (%d pages, method=%s)",
        len(text),
        path.name,
        pages,
        method,
    )
    return text, method, pages


def _extract_pdfplumber(path: Path) -> Tuple[str, str, int]:
    try:
        import pdfplumber

        pages_text = []
        page_count = 0
        with pdfplumber.open(str(path)) as pdf:
            page_count = len(pdf.pages)
            for page in pdf.pages:
                t = page.extract_text(x_tolerance=3, y_tolerance=3)
                if t:
                    pages_text.append(t)
        return "\n\n".join(pages_text), "pdfplumber", page_count
    except Exception as e:
        log.debug("pdfplumber failed for %s: %s", path.name, e)
        return "", "pdfplumber_failed", 0


def _extract_pypdf(path: Path) -> Tuple[str, str, int]:
    try:
        import pypdf

        pages_text = []
        with open(str(path), "rb") as f:
            reader = pypdf.PdfReader(f)
            page_count = len(reader.pages)
            for page in reader.pages:
                t = page.extract_text()
                if t:
                    pages_text.append(t)
        return "\n\n".join(pages_text), "pypdf", page_count
    except Exception as e:
        log.debug("pypdf failed for %s: %s", path.name, e)
        return "", "pypdf_failed", 0


def _clean_extracted_text(text: str) -> str:
    """Remove common PDF extraction artefacts."""
    # Collapse excessive whitespace
    text = re.sub(r"[ \t]{3,}", "  ", text)
    # Remove lone page numbers / headers that repeat every page
    text = re.sub(r"\n\d+\n", "\n", text)
    # Collapse more than 2 consecutive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ── PDF download helpers ──────────────────────────────────────────────────────


def _pdf_url_for_document(doc: Dict[str, Any]) -> Optional[str]:
    """
    Derive a PDF download URL for a document already in the database.
    Returns None if no PDF URL is determinable.
    """
    doc_id = doc.get("id", "")
    raw = doc.get("raw_json") or {}
    source = doc.get("source", "")

    # Federal Register — pdf_url is directly in the API response
    if "federal_register" in source or doc_id.startswith("FR-"):
        pdf_url = raw.get("pdf_url")
        if pdf_url:
            return pdf_url
        # Derive from html_url: append .pdf to the full document path
        # e.g. .../documents/2026/03/14/2026-05213/title-slug → .../title-slug.pdf
        html_url = doc.get("url") or raw.get("html_url") or ""
        if html_url and "federalregister.gov/documents/" in html_url:
            # Strip trailing slash and query string, then append .pdf
            clean = html_url.split("?")[0].rstrip("/")
            return clean + ".pdf"
        # Last resort: the /full_text/pdf/ path works for most but not all docs
        doc_num = doc_id.replace("FR-", "")
        if doc_num:
            return (
                f"https://www.federalregister.gov/documents/full_text/pdf/{doc_num}.pdf"
            )

    # EUR-Lex — deterministic URL from CELEX id
    if "eurlex" in source or doc_id.startswith("EU-CELEX-"):
        celex = doc_id.replace("EU-CELEX-", "")
        if celex:
            return (
                f"https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX:{celex}"
            )

    # UK legislation.gov.uk — construct from document URL pattern
    if doc.get("jurisdiction") == "GB":
        url = doc.get("url", "")
        # e.g. https://www.legislation.gov.uk/ukpga/2024/13/contents
        m = re.search(
            r"legislation\.gov\.uk/(ukpga|uksi|asp|anaw|asc|nia|apgb)/(\d{4})/(\d+)",
            url,
        )
        if m:
            dtype, year, num = m.group(1), m.group(2), m.group(3)
            return (
                f"https://www.legislation.gov.uk/{dtype}/{year}/{num}"
                f"/pdfs/{dtype}{year}{num}_en.pdf"
            )

    # GovInfo — for documents that carry a govinfo package id
    govinfo_id = raw.get("govinfo_package_id") or raw.get("package_id")
    if govinfo_id:
        from config.settings import GOVINFO_KEY

        if GOVINFO_KEY:
            return (
                f"https://api.govinfo.gov/packages/{govinfo_id}/pdf"
                f"?api_key={GOVINFO_KEY}"
            )

    return None


def _download_pdf(url: str, dest: Path, timeout: int = 60) -> bool:
    """Download a PDF from url to dest. Returns True on success."""
    import urllib.request
    import urllib.error

    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                ),
                "Accept": "application/pdf,*/*;q=0.9",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content_type = resp.headers.get("Content-Type", "")
            data = resp.read()
            if len(data) < 1000:
                log.warning(
                    "Downloaded file too small (%d bytes) from %s", len(data), url
                )
                return False
            # Accept application/pdf or octet-stream
            if "html" in content_type.lower() and b"%PDF" not in data[:8]:
                log.warning("URL returned HTML not PDF: %s", url)
                return False
        dest.write_bytes(data)
        log.info("Downloaded %d bytes → %s", len(data), dest.name)
        return True
    except Exception as e:
        log.warning("PDF download failed from %s: %s", url, e)
        return False


# ── Auto-download agent ───────────────────────────────────────────────────────


class PDFAutoDownloader:
    """
    Scans the database for documents that have a downloadable PDF
    and haven't been PDF-extracted yet. Downloads and extracts them.
    """

    def run(
        self, jurisdiction: Optional[str] = None, limit: int = 20, progress_cb=None
    ) -> Dict[str, Any]:
        """
        Auto-download PDFs for documents in the database.

        Returns a summary dict: {attempted, succeeded, failed, skipped}.
        """
        from utils.db import (
            get_all_documents,
            get_pdf_metadata,
            upsert_document,
            save_pdf_metadata,
        )

        docs = get_all_documents(jurisdiction=jurisdiction)
        results = {"attempted": 0, "succeeded": 0, "failed": 0, "skipped": 0}

        for doc in docs[: limit * 3]:  # fetch more candidates than limit
            if results["attempted"] >= limit:
                break

            # Skip if already PDF-extracted
            if get_pdf_metadata(doc["id"]):
                results["skipped"] += 1
                continue

            # Skip if full_text is already substantial (>2000 chars from API)
            if len(doc.get("full_text") or "") > 2000:
                results["skipped"] += 1
                continue

            # Skip documents that aren't AI-relevant — catches stale non-AI
            # docs that entered the DB before the keyword filter was tightened
            from utils.cache import is_ai_relevant as _is_ai

            title_and_text = f"{doc.get('title', '')} {doc.get('full_text', '') or ''}"
            if not _is_ai(title_and_text):
                results["skipped"] += 1
                continue

            pdf_url = _pdf_url_for_document(doc)
            if not pdf_url:
                results["skipped"] += 1
                continue

            results["attempted"] += 1
            if progress_cb:
                progress_cb(f"Downloading PDF: {doc.get('title', doc['id'])[:60]}")

            # Save to pdf store
            safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", doc["id"])[:80]
            pdf_path = PDF_STORE_DIR / f"{safe_id}.pdf"

            ok = _download_pdf(pdf_url, pdf_path)
            if not ok:
                results["failed"] += 1
                continue

            try:
                text, method, pages = extract_text_from_pdf(pdf_path)
            except Exception as e:
                log.error("Extraction failed for %s: %s", doc["id"], e)
                results["failed"] += 1
                continue

            if not text.strip():
                results["failed"] += 1
                continue

            # Update the document's full_text
            doc["full_text"] = text
            doc["origin"] = "pdf_auto"
            upsert_document(doc)

            # Record PDF metadata
            save_pdf_metadata(
                {
                    "document_id": doc["id"],
                    "pdf_path": str(pdf_path),
                    "pdf_url": pdf_url,
                    "page_count": pages,
                    "word_count": len(text.split()),
                    "extraction_method": method,
                    "extracted_at": datetime.utcnow(),
                    "origin": "pdf_auto",
                }
            )

            results["succeeded"] += 1
            log.info(
                "PDF auto-ingested: %s (%d pages, %d words)",
                doc["id"],
                pages,
                len(text.split()),
            )

        return results

    def candidates(self, jurisdiction: Optional[str] = None) -> List[Dict]:
        """
        List documents that have a PDF URL available but haven't been
        PDF-extracted yet. Used to populate the UI download panel.
        """
        from utils.db import get_all_documents, get_pdf_metadata

        docs = get_all_documents(jurisdiction=jurisdiction)
        candidates = []
        for doc in docs:
            if get_pdf_metadata(doc["id"]):
                continue  # already done
            pdf_url = _pdf_url_for_document(doc)
            if pdf_url:
                candidates.append(
                    {
                        "id": doc["id"],
                        "title": doc["title"],
                        "jurisdiction": doc["jurisdiction"],
                        "source": doc["source"],
                        "pdf_url": pdf_url,
                        "has_text": bool(doc.get("full_text")),
                        "text_length": len(doc.get("full_text") or ""),
                    }
                )
        return candidates


# ── Manual ingest (drop folder) ───────────────────────────────────────────────


class PDFManualIngestor:
    """
    Handles PDFs placed manually in the drop folder or uploaded via the UI.
    Accepts arbitrary metadata so any jurisdiction can be represented.
    """

    def list_inbox(self) -> List[Dict[str, Any]]:
        """Return all PDF files currently in the drop folder."""
        files = []
        for p in sorted(PDF_DROP_DIR.glob("*.pdf")):
            stat = p.stat()
            files.append(
                {
                    "filename": p.name,
                    "path": str(p),
                    "size_bytes": stat.st_size,
                    "size_kb": round(stat.st_size / 1024, 1),
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                }
            )
        return files

    def ingest(self, filename_or_path: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Ingest a PDF from the drop folder or a given path.

        metadata keys (all optional except title):
          title, jurisdiction, agency, doc_type, status, url,
          published_date, notes

        Returns the normalised document dict that was stored.
        """
        from utils.db import upsert_document, save_pdf_metadata, get_document

        # F-03 fix: reject absolute paths and verify the resolved path stays
        # inside PDF_DROP_DIR to prevent arbitrary filesystem reads.
        candidate = Path(filename_or_path)
        if candidate.is_absolute():
            raise ValueError(
                f"Absolute paths are not permitted for PDF ingest: {candidate.name!r}. "
                f"Place the file in the PDF inbox folder and use its filename."
            )
        # Strip any directory traversal components from the name
        safe_name = Path(filename_or_path).name
        safe_name = re.sub(r"[^a-zA-Z0-9._\-]", "_", safe_name)
        resolved = (PDF_DROP_DIR / safe_name).resolve()
        inbox_res = PDF_DROP_DIR.resolve()
        if not str(resolved).startswith(str(inbox_res)):
            raise ValueError(f"Path traversal rejected for: {safe_name!r}")
        src = resolved
        if not src.exists():
            raise FileNotFoundError(f"PDF not found in inbox: {safe_name!r}")

        # Extract text
        text, method, pages = extract_text_from_pdf(src)
        if not text.strip():
            raise ValueError(f"Could not extract any text from {src.name}")

        # Build a stable document ID
        title = metadata.get("title") or src.stem
        jur = metadata.get("jurisdiction") or "Unknown"
        doc_id = _make_pdf_doc_id(title, jur)

        # Check for duplicate
        if get_document(doc_id):
            log.info("PDF already ingested with id %s — updating text", doc_id)

        # Parse published_date
        published = None
        pd_raw = metadata.get("published_date")
        if pd_raw:
            for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
                try:
                    published = datetime.strptime(str(pd_raw)[:10], fmt)
                    break
                except ValueError:
                    continue

        doc = {
            "id": doc_id,
            "source": "pdf_manual",
            "jurisdiction": jur,
            "doc_type": metadata.get("doc_type") or "PDF Document",
            "title": title,
            "url": metadata.get("url") or "",
            "published_date": published,
            "agency": metadata.get("agency") or "",
            "status": metadata.get("status") or "Unknown",
            "full_text": text,
            "raw_json": {
                "origin": "pdf_manual",
                "original_filename": src.name,
                "page_count": pages,
                "word_count": len(text.split()),
                "notes": metadata.get("notes") or "",
            },
        }

        upsert_document(doc)

        # Move to stored folder
        stored_dir = PDF_STORE_DIR / "stored"
        stored_dir.mkdir(exist_ok=True)
        stored_path = stored_dir / src.name
        # Avoid overwrite collision
        if stored_path.exists():
            stored_path = stored_dir / f"{src.stem}_{doc_id[-6:]}.pdf"
        shutil.move(str(src), str(stored_path))

        save_pdf_metadata(
            {
                "document_id": doc_id,
                "pdf_path": str(stored_path),
                "pdf_url": metadata.get("url") or "",
                "page_count": pages,
                "word_count": len(text.split()),
                "extraction_method": method,
                "extracted_at": datetime.utcnow(),
                "origin": "pdf_manual",
            }
        )

        log.info(
            "Manual PDF ingested: %s (%s, %d pages, %d words)",
            doc_id,
            jur,
            pages,
            len(text.split()),
        )
        return doc

    def ingest_bytes(
        self, filename: str, data: bytes, metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Ingest a PDF from raw bytes (uploaded via the browser).
        Saves the file to the drop folder first, then calls ingest().
        """
        # F-02 fix: strip directory components and sanitize characters to
        # prevent path traversal (e.g. filename="../../etc/passwd").
        safe_name = Path(filename).name  # drops any directory parts
        safe_name = re.sub(r"[^a-zA-Z0-9._\-]", "_", safe_name)  # safe chars only
        if not safe_name.lower().endswith(".pdf"):
            safe_name = safe_name + ".pdf"

        dest = PDF_DROP_DIR / safe_name
        # Handle name collision
        if dest.exists():
            dest = PDF_DROP_DIR / f"{dest.stem}_{uuid.uuid4().hex[:6]}.pdf"
        dest.write_bytes(data)
        return self.ingest(str(dest), metadata)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_pdf_doc_id(title: str, jurisdiction: str) -> str:
    """Generate a stable, collision-resistant document ID for a PDF."""
    raw = f"{jurisdiction}::{title.lower().strip()}"
    slug = re.sub(r"[^a-z0-9]+", "-", raw)[:50].strip("-")
    h = hashlib.md5(raw.encode()).hexdigest()[:8]
    return f"PDF-{slug}-{h}"


def get_pdf_stats() -> Dict[str, Any]:
    """Return summary statistics about PDF ingestion."""
    from utils.db import get_all_pdf_metadata

    all_meta = get_all_pdf_metadata()
    auto = [m for m in all_meta if m.get("origin") == "pdf_auto"]
    manual = [m for m in all_meta if m.get("origin") == "pdf_manual"]
    inbox = list(PDF_DROP_DIR.glob("*.pdf"))
    return {
        "total_pdfs": len(all_meta),
        "auto_downloaded": len(auto),
        "manually_ingested": len(manual),
        "inbox_pending": len(inbox),
        "total_pages": sum(m.get("page_count", 0) for m in all_meta),
        "total_words": sum(m.get("word_count", 0) for m in all_meta),
        "pdf_store_dir": str(PDF_STORE_DIR),
        "pdf_inbox_dir": str(PDF_DROP_DIR),
    }
