"""
Universal Spatial Parser — Production-Grade PDF Table Extraction
================================================================

Uses pdfplumber.extract_words() to spatially reconstruct tables from ANY
Indian bank statement PDF.  Never relies on table-line detection or string
splitting.

Algorithm:
  1. Group words by Y-coordinate → horizontal text lines.
  2. Scan first ~30 lines for the HEADER row (keyword matching). Candidate
     lines that contain a date or an amount are rejected — they are
     transactions that merely mention words like "UPI transfer credit".
  3. Build column zones from header word X-positions.
  4. For every subsequent line, assign words to zones by X-overlap.
  5. Sticky header: the first header defines the columns. A header found on
     a later page only re-calibrates the zones when it has at least as many
     columns; otherwise the page is treated as pure data (nothing skipped).
  6. Return (header_names, rows) — ready for cleaner / merger pipeline.

Handles:
  HDFC, ICICI, SBI, Axis, Kotak, PNB, and any unknown bank.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

import pdfplumber  # type: ignore

from utils.logger import get_logger

logger = get_logger("parser.universal_spatial")

# Gap (pt) under which adjacent header words are merged into one column name.
# 6pt keeps "Txn Date" / "Value Date" and "Balance" / "Branch" apart.
_HDR_TOL = 6.0

# Keywords that commonly appear in bank statement headers
_HEADER_KW = frozenset({
    "date", "dt", "txn", "transaction", "tran", "value",
    "narration", "description", "particulars", "details", "remarks",
    "chq", "cheque", "ref", "reference", "instrument",
    "debit", "withdrawal", "withdrawl", "dr", "paid",
    "credit", "deposit", "cr", "received",
    "balance", "bal", "closing", "running",
    "amount", "amt",
})

# Date regex — matches at the START of text
_DATE_START_RE = re.compile(
    r'^('
    r'\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}'
    r'|\d{1,2}[-/.\s]+[A-Za-z]{3,9}[-/.\s]+\d{2,4}'
    r'|\d{4}[-/]\d{2}[-/]\d{2}'
    r'|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{2,4}'
    r')'
)


# ═══════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════

def extract(pdf_path: str) -> Tuple[Optional[List[str]], List[List[str]]]:
    """
    Extract all rows from a bank statement PDF using spatial word positioning.

    Returns:
        (header_names, data_rows)
        header_names: list of column name strings (exact from PDF)
        data_rows: list of lists, each inner list = one row's cell values
    """
    header, rows, _ = extract_with_raw(pdf_path)
    return header, rows


def extract_with_raw(
    pdf_path: str,
) -> Tuple[Optional[List[str]], List[List[str]], List[str]]:
    """Like :func:`extract`, but also returns the raw text lines (Raw sheet)
    collected in the same pass, so the PDF is only opened once."""
    all_rows: List[List[str]] = []
    raw_lines: List[str] = []
    header_names: Optional[List[str]] = None
    zones: Optional[List[Tuple[str, float, float]]] = None
    pages_processed = 0

    try:
        with pdfplumber.open(pdf_path) as pdf:
            num_pages = len(pdf.pages)
            logger.info("Universal spatial parser: %d pages", num_pages)

            for page_idx, page in enumerate(pdf.pages):
                page_num = page_idx + 1
                pages_processed = page_num

                # ── Extract words with bounding boxes ──
                raw_words = page.extract_words(
                    x_tolerance=3,
                    y_tolerance=3,
                    keep_blank_chars=True,
                    extra_attrs=["fontname", "size"],
                )

                # ── Raw text lines (for the Raw sheet) ──
                text = page.extract_text() or ""
                for line in text.split("\n"):
                    line = line.strip()
                    if line:
                        raw_lines.append(line)

                if not raw_words:
                    continue

                # ── Deduplicate exact-position words ──
                words = _dedupe_words(raw_words)

                # ── Group words into horizontal text lines ──
                lines = _group_into_lines(words)

                # ── Detect header on this page ──
                page_zones, header_idx = _find_header(lines)
                process_from = 0
                if page_zones:
                    if zones is None:
                        zones = page_zones
                        header_names = [z[0] for z in zones]
                        logger.info("Header detected on page %d: %s", page_num, header_names)
                        process_from = header_idx + 1
                    elif len(page_zones) >= len(zones):
                        # Repeated header on a later page: re-calibrate the
                        # column positions (keep the original names when the
                        # column count matches).
                        if len(page_zones) == len(zones):
                            zones = [(zones[i][0], z[1], z[2]) for i, z in enumerate(page_zones)]
                        else:
                            zones = page_zones
                        process_from = header_idx + 1
                    # else: a narrower "header" is almost certainly a data or
                    # footer line — keep the current zones and lose nothing.

                if zones is None:
                    # No header found yet on any page — skip data extraction
                    # but keep collecting raw lines
                    continue

                # ── Convert lines to rows using column zones ──
                for line_words in lines[process_from:]:
                    if not line_words:
                        continue

                    # Merge nearby words on the same line
                    merged = _merge_nearby_words(line_words, tolerance=5.0)

                    row = _assign_to_columns(merged, zones)

                    # Skip completely empty rows
                    if any(cell.strip() for cell in row):
                        all_rows.append(row)

                if page_num % 20 == 0 or page_num <= 2:
                    logger.info("  Page %d/%d: %d rows so far", page_num, num_pages, len(all_rows))

    except Exception as e:
        logger.exception("Spatial extraction failed: %s", e)

    logger.info(
        "Universal spatial parser: %d pages → %d data rows, %d raw lines",
        pages_processed, len(all_rows), len(raw_lines),
    )

    # If spatial extraction found nothing, try table fallback
    if not all_rows:
        logger.warning("Spatial extraction yielded 0 rows — trying table fallback")
        header_names, all_rows, _ = _table_fallback(pdf_path)

    return header_names, all_rows, raw_lines


def extract_raw_lines(pdf_path: str) -> List[str]:
    """Extract all raw text lines from the PDF (for Raw sheet)."""
    raw_lines: List[str] = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                for line in text.split("\n"):
                    line = line.strip()
                    if line:
                        raw_lines.append(line)
    except Exception as e:
        logger.exception("Raw text extraction failed: %s", e)
    return raw_lines


# ═══════════════════════════════════════════════════════════════════════════
# WORD GROUPING
# ═══════════════════════════════════════════════════════════════════════════

def _dedupe_words(raw_words: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Remove duplicate words at the exact same position."""
    seen: set = set()
    out: List[Dict[str, Any]] = []
    for w in raw_words:
        text = str(w.get("text", "")).strip()
        if not text:
            continue
        key = (round(w["x0"], 1), round(w["top"], 1), text)
        if key not in seen:
            seen.add(key)
            w["text"] = text
            out.append(w)
    return out


def _group_into_lines(
    words: List[Dict[str, Any]], tolerance: float = 3.0
) -> List[List[Dict[str, Any]]]:
    """Group words into horizontal text lines by Y-coordinate proximity."""
    if not words:
        return []

    words = sorted(words, key=lambda w: (w["top"], w["x0"]))
    lines: List[List[Dict[str, Any]]] = []
    current_line: List[Dict[str, Any]] = [words[0]]
    current_top = words[0]["top"]

    for w in words[1:]:
        if abs(w["top"] - current_top) <= tolerance:
            current_line.append(w)
        else:
            current_line.sort(key=lambda x: x["x0"])
            lines.append(current_line)
            current_line = [w]
            current_top = w["top"]

    if current_line:
        current_line.sort(key=lambda x: x["x0"])
        lines.append(current_line)

    return lines


def _merge_nearby_words(
    line: List[Dict[str, Any]], tolerance: float = 5.0
) -> List[Dict[str, Any]]:
    """Merge words on the same line that are within `tolerance` pixels."""
    if not line:
        return []

    line = sorted(line, key=lambda w: w["x0"])
    merged: List[Dict[str, Any]] = []
    current = dict(line[0])

    for w in line[1:]:
        gap = w["x0"] - current.get("x1", current["x0"] + 10)
        if gap <= tolerance:
            current["text"] = current["text"] + " " + w["text"]
            current["x1"] = w.get("x1", w["x0"] + 10)
        else:
            merged.append(current)
            current = dict(w)

    merged.append(current)
    return merged


# ═══════════════════════════════════════════════════════════════════════════
# HEADER DETECTION
# ═══════════════════════════════════════════════════════════════════════════

def _find_header(
    lines: List[List[Dict[str, Any]]], max_scan: int = 30
) -> Tuple[Optional[List[Tuple[str, float, float]]], int]:
    """
    Detect the header row and build strict column zones.

    Returns:
        (zones, header_index)
        zones: list of (column_name, x_start, x_end)
        header_index: index of the header line in the `lines` list
    """
    best_score = 0
    best_zones: Optional[List[Tuple[str, float, float]]] = None
    best_idx = 0

    for idx, line in enumerate(lines[:max_scan]):
        # Merge header words (multi-word headers like "Value Date")
        merged_line = _merge_nearby_words(line, tolerance=_HDR_TOL)

        # Score by keyword matching
        text_combined = " ".join(w["text"] for w in merged_line).lower()
        score = sum(1 for kw in _HEADER_KW if kw in text_combined)

        if score < 3 or score <= best_score:
            continue
        if not _looks_like_header(merged_line, text_combined):
            continue

        zones: List[Tuple[str, float, float]] = []
        for i, w in enumerate(merged_line):
            col_name = w["text"].strip()
            x_start = w["x0"] - 5.0
            x_end = (
                merged_line[i + 1]["x0"] - 2.0
                if i + 1 < len(merged_line)
                else 9999.0
            )
            zones.append((col_name, x_start, x_end))

        best_score = score
        best_idx = idx
        best_zones = zones

    return best_zones, best_idx


_AMOUNT_RE = re.compile(r"\d[\d,]*\.\d{2}\b")
_ANY_DATE_RE = re.compile(
    r"\b(\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}"
    r"|\d{1,2}[-/.\s][A-Za-z]{3,9}[-/.\s]\d{2,4}"
    r"|\d{4}[-/]\d{2}[-/]\d{2})\b"
)


def _looks_like_header(merged_line: List[Dict[str, Any]], text: str) -> bool:
    """Reject transaction lines that merely contain header-ish words."""
    if len(merged_line) < 3:
        return False
    if _AMOUNT_RE.search(text) or _ANY_DATE_RE.search(text):
        return False
    return True


# ═══════════════════════════════════════════════════════════════════════════
# COLUMN ASSIGNMENT
# ═══════════════════════════════════════════════════════════════════════════

def _assign_to_columns(
    words: List[Dict[str, Any]],
    zones: List[Tuple[str, float, float]],
) -> List[str]:
    """Assign each word to a column zone based on its X-coordinate."""
    row = [""] * len(zones)

    for w in words:
        x_center = (w["x0"] + w.get("x1", w["x0"] + 10)) / 2.0
        best_zone = -1
        best_dist = float("inf")

        for i, (_, z_start, z_end) in enumerate(zones):
            if z_start <= x_center < z_end:
                best_zone = i
                break
            # Track closest zone for stray words
            mid = (z_start + z_end) / 2.0
            dist = abs(x_center - mid)
            if dist < best_dist:
                best_dist = dist
                best_zone = i

        if best_zone >= 0:
            cell = row[best_zone]
            text = w["text"].strip()
            if cell:
                row[best_zone] = cell + " " + text
            else:
                row[best_zone] = text

    # Clean extra whitespace
    return [re.sub(r"\s+", " ", cell).strip() for cell in row]


# ═══════════════════════════════════════════════════════════════════════════
# TABLE FALLBACK (for PDFs where extract_words fails)
# ═══════════════════════════════════════════════════════════════════════════

def _table_fallback(
    pdf_path: str,
) -> Tuple[Optional[List[str]], List[List[str]], List[str]]:
    """Fallback to pdfplumber table extraction when spatial parsing fails."""
    header: Optional[List[str]] = None
    all_rows: List[List[str]] = []
    raw_lines: List[str] = []

    strategies = [
        {"vertical_strategy": "lines", "horizontal_strategy": "lines",
         "intersection_tolerance": 5},
        {"vertical_strategy": "text", "horizontal_strategy": "text"},
        {"vertical_strategy": "text", "horizontal_strategy": "lines"},
    ]

    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                # Collect raw text
                text = page.extract_text() or ""
                for line in text.split("\n"):
                    if line.strip():
                        raw_lines.append(line.strip())

                # Try table strategies
                for strat in strategies:
                    try:
                        tables = page.extract_tables(strat)
                    except Exception:
                        continue
                    if not tables:
                        continue

                    for tbl in tables:
                        if not tbl or len(tbl) < 2:
                            continue
                        hdr, rows = _split_header_data(tbl)
                        if hdr and header is None:
                            header = hdr
                        all_rows.extend(rows)

                    if all_rows:
                        break  # This strategy worked for this page

    except Exception as e:
        logger.exception("Table fallback failed: %s", e)

    logger.info("Table fallback: %d rows, header=%s", len(all_rows), header)
    return header, all_rows, raw_lines


def _split_header_data(
    raw_table: list,
) -> Tuple[Optional[List[str]], List[List[str]]]:
    """Split a raw table into header + data rows."""
    max_cols = max(len(r) for r in raw_table if r)
    norm = [
        [str(c).strip() if c else "" for c in r] + [""] * (max_cols - len(r))
        for r in raw_table
    ]

    best_idx = 0
    best_score = 0
    for i in range(min(8, len(norm))):
        text = " ".join(norm[i]).lower().replace("\n", " ")
        score = sum(1 for kw in _HEADER_KW if kw in text)
        if score > best_score:
            best_score = score
            best_idx = i

    if best_score >= 2:
        header = [c.replace("\n", " ").strip() for c in norm[best_idx]]
        data = norm[best_idx + 1:]
    else:
        header = None
        data = norm

    return header, data
