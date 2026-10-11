"""
Extractor — Streaming page-by-page PDF table extraction.

Processes ONE page at a time (constant memory).
If pdfplumber fails for a page → falls back to Camelot for THAT page only.
Never skips a page even if extraction errors occur.
"""

import re
from typing import Generator, List, Optional, Tuple

import pdfplumber  # type: ignore

from utils.logger import get_logger

logger = get_logger("extractor")

_HEADER_KW = frozenset({
    "date", "description", "particulars", "narration", "transaction",
    "debit", "withdrawal", "credit", "deposit", "balance",
    "ref", "reference", "cheque", "chq",
})

# pdfplumber strategies — ordered from most structured to most relaxed
_STRATEGIES = [
    {"vertical_strategy": "lines", "horizontal_strategy": "lines",
     "intersection_tolerance": 5},
    {"vertical_strategy": "text",  "horizontal_strategy": "text"},
    {"vertical_strategy": "text",  "horizontal_strategy": "lines"},
]


def extract_all_rows(pdf_path: str) -> Tuple[Optional[List[str]], List[List[str]]]:
    """
    Extract ALL rows from ALL pages of the PDF.

    Returns (header, rows) where:
      header = list of column names (or None)
      rows   = list of lists (each inner list is one row)

    Internally streams page-by-page for constant memory usage.
    """
    header: Optional[List[str]] = None
    all_rows: List[List[str]] = []
    total_pages = 0
    pages_with_data = 0

    for page_num, pg_header, pg_rows in _stream_pages(pdf_path):
        total_pages = page_num

        if not pg_rows:
            continue

        pages_with_data += 1

        if header is None and pg_header is not None:
            header = pg_header

        all_rows.extend(pg_rows)

        if page_num % 10 == 0 or page_num <= 2:
            logger.info("  Page %d/%s: %d rows so far",
                        page_num, "?", len(all_rows))

    logger.info(
        "Extraction complete: %d pages scanned, %d had data, %d total raw rows",
        total_pages, pages_with_data, len(all_rows),
    )
    return header, all_rows


# ---------------------------------------------------------------------------
# Streaming generator
# ---------------------------------------------------------------------------

def _stream_pages(
    pdf_path: str,
) -> Generator[Tuple[int, Optional[List[str]], List[List[str]]], None, None]:
    """Yield (page_number, header_or_None, data_rows) per page."""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            num_pages = len(pdf.pages)
            logger.info("PDF opened: %d pages", num_pages)

            for idx, page in enumerate(pdf.pages):
                page_num = idx + 1
                pg_header = None
                pg_rows: List[List[str]] = []

                # Try each pdfplumber strategy
                for strat in _STRATEGIES:
                    try:
                        tables = page.extract_tables(strat)
                    except Exception:
                        continue
                    if not tables:
                        continue
                    for raw_tbl in tables:
                        if not raw_tbl or len(raw_tbl) < 2:
                            continue
                        hdr, rows = _split_header(raw_tbl)
                        if hdr and pg_header is None:
                            pg_header = hdr
                        pg_rows.extend(rows)
                    if pg_rows:
                        break

                # Per-page Camelot fallback
                if not pg_rows:
                    hdr, rows = _camelot_page(pdf_path, page_num)
                    if rows:
                        if hdr and pg_header is None:
                            pg_header = hdr
                        pg_rows = rows
                        logger.info(
                            "  Page %d: recovered %d rows via Camelot", page_num, len(rows),
                        )

                # Last resort: raw text splitting
                if not pg_rows:
                    try:
                        text = page.extract_text()
                        if text:
                            hdr, rows = _text_to_rows(text)
                            if rows:
                                if hdr and pg_header is None:
                                    pg_header = hdr
                                pg_rows = rows
                    except Exception:
                        pass

                yield page_num, pg_header, pg_rows

    except Exception as e:
        logger.exception("Failed to open PDF %s: %s", pdf_path, e)


# ---------------------------------------------------------------------------
# Per-page Camelot (avoids full-file reprocess)
# ---------------------------------------------------------------------------

def _camelot_page(
    pdf_path: str, page_num: int,
) -> Tuple[Optional[List[str]], List[List[str]]]:
    try:
        import camelot  # type: ignore
    except ImportError:
        return None, []

    for flavour in ("lattice", "stream"):
        try:
            tables = camelot.read_pdf(
                pdf_path, pages=str(page_num), flavor=flavour,
                strip_text="\n", suppress_stdout=True,
            )
            for t in tables:
                df = t.df
                if df.shape[0] > 1:
                    header = [str(c).strip() for c in df.iloc[0]]
                    rows = [[str(c) for c in r] for r in df.iloc[1:].values.tolist()]
                    return header, rows
        except Exception:
            continue
    return None, []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _split_header(
    raw_table: list,
) -> Tuple[Optional[List[str]], List[List[str]]]:
    """Detect the real header row and split from data rows."""
    max_cols = max(len(r) for r in raw_table if r)
    norm = [
        [str(c).strip() if c else "" for c in r] + [""] * (max_cols - len(r))
        for r in raw_table
    ]

    best_i, best_score = 0, 0
    for i in range(min(8, len(norm))):
        text = " ".join(norm[i]).lower().replace("\n", " ")
        score = sum(1 for kw in _HEADER_KW if kw in text)
        if score > best_score:
            best_score = score
            best_i = i

    if best_score >= 2:
        header = [c.replace("\n", " ").strip() for c in norm[best_i]]
        data = norm[best_i + 1:]
    else:
        header = None
        data = norm
    return header, data


def _text_to_rows(text: str) -> Tuple[Optional[List[str]], List[List[str]]]:
    """Heuristic: split raw page text into approximate table rows."""
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if len(lines) < 2:
        return None, []
    table = [
        re.split(r"\s{2,}", line)
        for line in lines
        if len(re.split(r"\s{2,}", line)) >= 2
    ]
    if len(table) < 2:
        return None, []
    return _split_header(table)
