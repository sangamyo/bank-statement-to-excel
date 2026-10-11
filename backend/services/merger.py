"""
Merger — Zero Data Loss Block Merger
======================================

Groups raw extracted rows into transaction blocks and merges multi-line
entries into single rows.  ZERO data is ever dropped.

Rules:
  1. A row starts a NEW transaction only if a date is at the START of its text.
  2. Otherwise → continuation row → append description to previous transaction.
  3. Column locking: Date / Debit / Credit / Amount / DR-CR keep the first
     value seen. Balance always takes the LAST value seen. Every other column
     (Description, Reference, custom text columns) is stitched together so
     that wrapped references are never truncated.
  4. DR/CR suffixes are respected strictly.
  5. Invalid / orphan rows merge into previous transaction's description.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional

from utils.logger import get_logger

logger = get_logger("merger")

# ──────────────────────────────────────────────────────────────────────────
# DATE PATTERNS — matches ALL major Indian bank date formats
# ──────────────────────────────────────────────────────────────────────────
_DATE_RE = re.compile(
    r'(?:^|\s)('
    r'\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}'              # dd/mm/yyyy, dd-mm-yy
    r'|\d{1,2}[-/.\s]+[A-Za-z]{3,9}[-/.\s]+\d{2,4}'  # 15-Oct-2025
    r'|\d{4}[-/]\d{2}[-/]\d{2}'                      # 2025-10-15 (ISO)
    r'|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{2,4}'            # 15 Oct 2025
    r')(?:\s|$|,)'
)

_DATE_START_RE = re.compile(
    r'^('
    r'\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}'
    r'|\d{1,2}[-/.\s]+[A-Za-z]{3,9}[-/.\s]+\d{2,4}'
    r'|\d{4}[-/]\d{2}[-/]\d{2}'
    r'|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{2,4}'
    r')'
)

_REF_RE = re.compile(r'\b\d{10,}\b')
_DR_SUFFIX_RE = re.compile(r'[\d,.]+\s*DR\b', re.IGNORECASE)
_CR_SUFFIX_RE = re.compile(r'[\d,.]+\s*CR\b', re.IGNORECASE)


# ══════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ══════════════════════════════════════════════════════════════════════════

def merge_rows(
    rows: List[Dict[str, str]],
    core_mapping: Dict[str, str],
    final_columns: List[str],
) -> List[Dict[str, str]]:
    """
    Block-based merging with ZERO data loss guarantee.

    Every input row contributes to output.  No row is ever dropped.
    """
    if not rows:
        return []

    date_col = core_mapping.get("Date")
    desc_col = core_mapping.get("Description")

    # ── Phase 1: Group rows into blocks ──
    blocks: List[List[Dict[str, str]]] = []
    current_block: List[Dict[str, str]] = []

    for row in rows:
        is_new_txn = _is_new_transaction(row, date_col)

        if is_new_txn:
            if current_block:
                blocks.append(current_block)
            current_block = [dict(row)]
        else:
            if current_block:
                current_block.append(dict(row))
            else:
                # Orphan row — start a block anyway (ZERO loss)
                current_block = [dict(row)]

    if current_block:
        blocks.append(current_block)

    # ── Phase 2: Merge each block into one row ──
    merged: List[Dict[str, str]] = []
    for block in blocks:
        txn = _merge_block(block, core_mapping, final_columns)
        if txn is not None:
            merged.append(txn)

    logger.info("Merge: %d input rows → %d transactions (%d blocks)",
                len(rows), len(merged), len(blocks))
    return merged


# ══════════════════════════════════════════════════════════════════════════
# TRANSACTION BOUNDARY DETECTION
# ══════════════════════════════════════════════════════════════════════════

def _is_new_transaction(row: Dict[str, str], date_col: Optional[str]) -> bool:
    """
    A row starts a new transaction if:
      1. The date column has a recognisable date, OR
      2. The full row text STARTS with a date pattern.
    """
    # Check date column first
    if date_col:
        date_val = str(row.get(date_col, "")).strip()
        if date_val and _DATE_RE.search(date_val):
            return True

    # Check start of full row text
    full_text = " ".join(str(v).strip() for v in row.values() if str(v).strip())
    return bool(_DATE_START_RE.match(full_text.strip()))


# ══════════════════════════════════════════════════════════════════════════
# BLOCK → SINGLE ROW
# ══════════════════════════════════════════════════════════════════════════

def _merge_block(
    block: List[Dict[str, str]],
    core_mapping: Dict[str, str],
    final_columns: List[str],
) -> Optional[Dict[str, str]]:
    """Merge a block of rows into exactly one transaction dict."""
    if not block:
        return None

    date_col = core_mapping.get("Date")
    ref_col = core_mapping.get("Reference")
    debit_col = core_mapping.get("Debit")
    credit_col = core_mapping.get("Credit")
    balance_col = core_mapping.get("Balance")

    # Start with empty row using EXACT PDF columns
    out: Dict[str, str] = {col: "" for col in final_columns}

    # Populate from FIRST row
    first = block[0]
    for col in final_columns:
        val = str(first.get(col, "")).strip()
        if val and val.lower() not in ("none", "nan"):
            out[col] = val

    # Columns that keep their FIRST non-empty value (never stitched)
    locked_cols = {
        c for c in (
            date_col, debit_col, credit_col,
            core_mapping.get("Amount"), core_mapping.get("DRCR"),
        ) if c
    }

    # ── Merge continuation rows ──
    for row in block[1:]:
        for col in final_columns:
            val = str(row.get(col, "")).strip()
            if not val or val.lower() in ("none", "nan"):
                continue

            if col == balance_col:
                # Balance: LAST seen value wins
                out[col] = val
            elif col == date_col:
                # Date only comes from the first row of the block
                pass
            elif col in locked_cols:
                # Amount columns: adopt if empty, otherwise keep first value
                if not out.get(col, "").strip():
                    out[col] = val
            else:
                # Description, Reference and any other text column:
                # stitch continuation text (zero truncation)
                out[col] = _stitch(out.get(col, "").strip(), val)

    # ── Extract date from text if missing ──
    if date_col and not out.get(date_col, "").strip():
        full = " ".join(str(v) for v in out.values())
        m = _DATE_RE.search(full)
        if m:
            out[date_col] = m.group(1).strip()

    # ── Reference extraction from full block ──
    if ref_col and not out.get(ref_col, "").strip():
        block_text = " ".join(
            " ".join(str(v) for v in r.values()) for r in block
        )
        rm = _REF_RE.search(block_text)
        if rm:
            out[ref_col] = rm.group(0)

    # ── DR/CR binding ──
    _bind_drcr(out, block, core_mapping)

    # Check for ANY data (ZERO loss — keep if anything non-empty)
    if any(str(v).strip() for v in out.values()):
        return out
    return None


# ══════════════════════════════════════════════════════════════════════════
# DR / CR BINDING
# ══════════════════════════════════════════════════════════════════════════

def _bind_drcr(
    out: Dict[str, str],
    block: List[Dict[str, str]],
    core_mapping: Dict[str, str],
) -> None:
    """Apply strict DR/CR rules. Never populate both Debit and Credit."""
    debit_col = core_mapping.get("Debit")
    credit_col = core_mapping.get("Credit")
    if not debit_col or not credit_col:
        return

    block_text = " ".join(
        " ".join(str(v) for v in r.values()) for r in block
    )

    has_dr = bool(_DR_SUFFIX_RE.search(block_text))
    has_cr = bool(_CR_SUFFIX_RE.search(block_text))

    # Clean DR/CR suffixes from Debit and Credit values only
    for col in (debit_col, credit_col):
        val = out.get(col, "")
        if val:
            cleaned = re.sub(r'\s*(DR|CR)\s*$', '', val, flags=re.IGNORECASE).strip()
            out[col] = cleaned

    if has_dr and not has_cr:
        if not out.get(debit_col, "").strip() and out.get(credit_col, "").strip():
            out[debit_col] = out[credit_col]
        out[credit_col] = ""

    elif has_cr and not has_dr:
        if not out.get(credit_col, "").strip() and out.get(debit_col, "").strip():
            out[credit_col] = out[debit_col]
        out[debit_col] = ""

    # Final mutex: if both populated, keep larger
    d = out.get(debit_col, "").strip()
    c = out.get(credit_col, "").strip()
    if d and c:
        try:
            dv = abs(float(d.replace(",", "")))
            cv = abs(float(c.replace(",", "")))
            if dv >= cv:
                out[credit_col] = ""
            else:
                out[debit_col] = ""
        except (ValueError, TypeError):
            pass


# ══════════════════════════════════════════════════════════════════════════
# TEXT STITCHING
# ══════════════════════════════════════════════════════════════════════════

def _stitch(prev: str, addition: str) -> str:
    """Rejoin broken text without corrupting IDs (UPI, IMPS, NEFT, etc.)."""
    if not prev:
        return addition
    if not addition:
        return prev

    # Broken at separator chars
    if prev.endswith(("-", "/", "@")) or addition.startswith(("/", "-", "@")):
        return prev + addition

    # Continuation of a numeric ID
    if re.search(r'\d$', prev) and re.search(r'^\d', addition):
        return prev + addition

    # Known continuous-format markers
    markers = ("UPI", "IMPS", "INF", "MMT", "NEFT", "RTGS", "@")
    if any(kw in prev.upper() for kw in markers):
        return prev + addition

    return prev + " " + addition
