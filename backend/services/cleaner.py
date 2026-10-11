"""
Cleaner — Bank-Aware Dynamic Column Engine
=============================================

This is the UNIVERSAL column-mapping and data-cleaning engine.
It works by:
  1. Detecting column ROLES from ANY header row dynamically
  2. Applying bank-specific post-processing rules
  3. Cleaning amounts, dates, and descriptions universally

Supports all Indian banks:
  HDFC, ICICI, Axis, SBI, Kotak, PNB, and unknowns.

STRICT RULES:
  - Column names are PRESERVED exactly as in the PDF
  - NEVER drops a row just because its date is unparseable
  - ZERO data loss
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

import pandas as pd

from utils.logger import get_logger

logger = get_logger("cleaner")


# ═══════════════════════════════════════════════════════════════════════════
# DYNAMIC COLUMN DETECTION PATTERNS
# ═══════════════════════════════════════════════════════════════════════════
# Priority ordered: first match wins per role.
# Covers HDFC, ICICI, Axis, SBI, Kotak, PNB, and generic.

_COL_PATTERNS = {
    "Date": [
        "txn date", "transaction date", "posting date", "tran date",
        "trans date", "value date", "date",
    ],
    "Description": [
        "narration", "particulars", "description", "details",
        "transaction details", "transaction particular", "remarks", "memo",
    ],
    "Reference": [
        "chq./ref.no.", "chq./ref.no", "chq no.", "chq no", "cheque no",
        "cheque", "instrument", "ref no.", "ref no", "ref",
        "utr", "transaction id", "tran id",
    ],
    "Debit": [
        "withdrawal amt.", "withdrawal amt", "withdrawal amount",
        "withdrawal", "withdrawl",                    # ICICI typo
        "debit amount", "debit amt", "debit",
        "dr amount", "dr amt", "dr",
        "paid out",
    ],
    "Credit": [
        "deposit amt.", "deposit amt", "deposit amount",
        "deposit", "credit amount", "credit amt", "credit",
        "cr amount", "cr amt", "cr",
        "paid in", "received",
    ],
    "Balance": [
        "closing balance", "running balance", "available balance",
        "balance (inr)", "balance(inr)", "balance",
        "bal", "running bal",
    ],
    "Amount": [
        "amount (inr)", "amount(inr)", "transaction amount",
        "txn amount", "amount", "amt",
    ],
    "DRCR": [
        "dr/cr", "dr / cr", "cr/dr", "cr / dr",
        "type", "txn type", "transaction type",
    ],
}

# Pre-compiled junk row detection
_JUNK_RE = re.compile("|".join([
    r"important information", r"page \d+", r"page no", r"statement of account",
    r"statement generated", r"current account transaction", r"for queries",
    r"opening balance", r"brought forward", r"hdfc bank limited",
    r"end of statement", r"ensure safety", r"commonly used narration",
    r"rbi mandates", r"registered office", r"scan for", r"never share",
    r"contact us", r"branch address", r"complimentary insurance",
    r"deposit.*insured", r"goods and services tax",
    r"www\.kotak", r"www\.hdfcbank", r"www\.icici", r"www\.sbi",
    r"cin:\s*[a-z]", r"account details",
    # Repeated header rows (from multi-page PDFs)
    r"^date\s+narration\s+chq", r"^date\s+description",
    r"^tran date\s+val", r"^value date\s+transaction",
    r"^withdrawal\s+deposit\s+balance", r"^debit\s+credit\s+balance",
]), re.IGNORECASE)

# Date detection regex
_DATE_RE = re.compile(
    r'(?:^|\s)('
    r'\d{1,2}[-/.\s]+[A-Za-z]{3,9}[-/.\s]+\d{2,4}'
    r'|\d{1,2}[-/.\s]+\d{1,2}[-/.\s]+\d{2,4}'
    r'|\d{4}[-/]\d{2}[-/]\d{2}'
    r')(?:\s|$)'
)

# PNB / SBI balance suffix
_BAL_SUFFIX_RE = re.compile(r'\s*(Cr\.?|Dr\.?)\s*$', re.IGNORECASE)


# ═══════════════════════════════════════════════════════════════════════════
# PUBLIC API: map_columns
# ═══════════════════════════════════════════════════════════════════════════

def map_columns(
    header: Optional[List[str]],
    rows: List[List[str]],
) -> Tuple[List[Dict[str, str]], Dict[str, str], List[str]]:
    """
    Map raw rows into dicts using the EXACT columns found in the PDF.

    Returns:
      1. row_dicts:     list of dicts with exact PDF column keys
      2. core_mapping:  internal key → PDF column name
      3. final_columns: column order as in the PDF
    """
    if not rows:
        return [], {}, []

    ncols = max(len(r) for r in rows)
    if header:
        ncols = max(ncols, len(header))

    # Normalise row lengths
    rows = [r + [""] * (ncols - len(r)) for r in rows]

    # ── Build final_columns from header ──
    final_columns: List[str] = []
    if header:
        for i, h in enumerate(header):
            clean = str(h).strip()
            col = clean if clean else f"Column {i+1}"
            # Ensure uniqueness
            base = col
            counter = 2
            while col in final_columns:
                col = f"{base} {counter}"
                counter += 1
            final_columns.append(col)

        for i in range(len(header), ncols):
            final_columns.append(f"Column {i+1}")
    else:
        final_columns = [f"Column {i+1}" for i in range(ncols)]

    # ── Match columns to internal roles ──
    core_mapping: Dict[str, str] = {}
    used: set = set()

    for col_name in final_columns:
        role = _match_column(col_name)
        if role and role not in used:
            core_mapping[role] = col_name
            used.add(role)

    # ── Handle Axis "Amount" + "DR/CR" pattern ──
    # If we found Amount and DRCR but NOT separate Debit/Credit,
    # we'll handle the split in coerce_numerics
    if "Amount" in core_mapping and "Debit" not in core_mapping:
        logger.info("Detected Amount+DR/CR pattern (Axis/PNB style)")
        # We'll create virtual Debit/Credit during coerce_numerics

    # ── Fallback: detect Date column by content sampling ──
    if "Date" not in used:
        for i, col_name in enumerate(final_columns):
            if col_name in core_mapping.values():
                continue
            sample = [r[i] for r in rows[:30] if r[i].strip()]
            date_hits = sum(1 for s in sample if _DATE_RE.search(s))
            if sample and date_hits / max(len(sample), 1) > 0.4:
                core_mapping["Date"] = col_name
                used.add("Date")
                break

    # ── Convert rows to dicts ──
    result: List[Dict[str, str]] = []
    for row in rows:
        d: Dict[str, str] = {col: "" for col in final_columns}
        for i, val in enumerate(row):
            if i < len(final_columns):
                d[final_columns[i]] = str(val).strip() if val else ""
        result.append(d)

    logger.info("Columns detected: %s", final_columns)
    logger.info("Core mapping: %s", core_mapping)
    return result, core_mapping, final_columns


# ═══════════════════════════════════════════════════════════════════════════
# PUBLIC API: remove_junk
# ═══════════════════════════════════════════════════════════════════════════

def remove_junk(rows: List[Dict[str, str]], core_mapping: Optional[Dict[str, str]] = None) -> List[Dict[str, str]]:
    """Remove rows matching known non-transaction patterns.

    A row that has BOTH a date and an amount is a real transaction and is
    never dropped, even if its narration happens to match a junk pattern
    (e.g. "... PAGE 2 ..." or "OPENING BALANCE TRANSFER").
    """
    before = len(rows)
    cleaned = []
    core_mapping = core_mapping or {}
    date_col = core_mapping.get("Date")
    num_cols = [core_mapping.get(k) for k in ("Debit", "Credit", "Amount")]
    num_cols = [c for c in num_cols if c]
    for row in rows:
        text = " ".join(str(v) for v in row.values()).strip()
        if not text:
            continue
        has_date = bool(date_col and _DATE_RE.search(" " + str(row.get(date_col, "")) + " "))
        has_amt = any(_parse_num(row.get(c, "")) for c in num_cols)
        if has_date and has_amt:
            cleaned.append(row)
            continue
        if _JUNK_RE.search(text):
            continue
        cleaned.append(row)
    removed = before - len(cleaned)
    if removed:
        logger.info("Removed %d junk rows", removed)
    return cleaned


# ═══════════════════════════════════════════════════════════════════════════
# PUBLIC API: parse_dates
# ═══════════════════════════════════════════════════════════════════════════

def parse_dates(
    rows: List[Dict[str, str]], core_mapping: Dict[str, str]
) -> List[Dict[str, str]]:
    """Parse Date field safely. NEVER drops rows."""
    import dateutil.parser

    date_col = core_mapping.get("Date")
    if not date_col:
        return rows

    valid = 0
    for row in rows:
        raw = row.get(date_col, "").strip()
        if not raw:
            continue

        m = _DATE_RE.search(raw)
        date_str = m.group(1) if m else raw

        try:
            parsed = dateutil.parser.parse(date_str, dayfirst=True)
            row[date_col] = parsed.strftime("%Y-%m-%d")
            valid += 1
        except Exception:
            parsed = pd.to_datetime(date_str, errors="coerce", dayfirst=True)
            if pd.notna(parsed):
                row[date_col] = parsed.strftime("%Y-%m-%d")
                valid += 1

    logger.info("Dates parsed: %d valid, %d unparseable (kept)", valid, len(rows) - valid)
    return rows


# ═══════════════════════════════════════════════════════════════════════════
# PUBLIC API: coerce_numerics (BANK-AWARE)
# ═══════════════════════════════════════════════════════════════════════════

def coerce_numerics(
    rows: List[Dict[str, str]],
    core_mapping: Dict[str, str],
    bank: str = "unknown",
) -> List[Dict[str, str]]:
    """
    Convert Debit/Credit/Balance to clean numeric strings.
    Handles bank-specific patterns:
      - Axis: "Amount" + "DR/CR" columns
      - PNB/SBI: "Cr."/"Dr." suffix on balance
      - ICICI: standard with possible 'NA' values
      - HDFC: standard format
    """
    debit_col = core_mapping.get("Debit")
    credit_col = core_mapping.get("Credit")
    balance_col = core_mapping.get("Balance")
    amount_col = core_mapping.get("Amount")
    drcr_col = core_mapping.get("DRCR")

    for row in rows:
        # ── Handle Axis/PNB Amount + DR/CR pattern ──
        if amount_col and drcr_col:
            amt_str = row.get(amount_col, "").strip()
            drcr_str = row.get(drcr_col, "").strip().upper()
            amt_val = _parse_num(amt_str)

            if amt_val is not None and amt_val != 0:
                if "DR" in drcr_str:
                    if debit_col:
                        row[debit_col] = str(amt_val)
                    if credit_col:
                        row[credit_col] = ""
                elif "CR" in drcr_str:
                    if credit_col:
                        row[credit_col] = str(amt_val)
                    if debit_col:
                        row[debit_col] = ""
                else:
                    # No DR/CR indicator — keep in Amount column as-is
                    pass

        # ── Handle Axis: DR/CR embedded in amount value (e.g. "6277.00 DR") ──
        for col in [debit_col, credit_col]:
            if not col:
                continue
            val_str = str(row.get(col, "")).upper().strip()
            if "DR" in val_str and debit_col:
                clean = _parse_num(val_str.replace("DR", "").strip())
                if clean is not None:
                    row[debit_col] = str(clean)
                    if credit_col and col != debit_col:
                        row[col] = ""
                    elif credit_col:
                        row[credit_col] = ""
            elif "CR" in val_str and credit_col:
                clean = _parse_num(val_str.replace("CR", "").strip())
                if clean is not None:
                    row[credit_col] = str(clean)
                    if debit_col and col != credit_col:
                        row[col] = ""
                    elif debit_col:
                        row[debit_col] = ""

        # ── Handle PNB/SBI: Cr./Dr. suffix on balance (e.g. "16631.85 Cr.") ──
        if balance_col:
            bal_str = row.get(balance_col, "").strip()
            bal_str = _BAL_SUFFIX_RE.sub("", bal_str).strip()
            bal_val = _parse_num(bal_str)
            row[balance_col] = str(bal_val) if bal_val is not None else ""

        # ── Clean Debit/Credit values ──
        for col in [debit_col, credit_col]:
            if not col:
                continue
            val = _parse_num(row.get(col, ""))
            row[col] = str(val) if val is not None else ""

    return rows


# ═══════════════════════════════════════════════════════════════════════════
# PUBLIC API: enforce_mutex
# ═══════════════════════════════════════════════════════════════════════════

def enforce_mutex(
    rows: List[Dict[str, str]],
    core_mapping: Dict[str, str],
    bank: str = "unknown",
) -> List[Dict[str, str]]:
    """Ensure Debit and Credit are mutually exclusive per row."""
    debit_col = core_mapping.get("Debit")
    credit_col = core_mapping.get("Credit")

    if not debit_col or not credit_col:
        return rows

    for row in rows:
        d = _parse_num(row.get(debit_col, ""))
        c = _parse_num(row.get(credit_col, ""))
        has_d = d is not None and d != 0
        has_c = c is not None and c != 0

        if has_d and has_c:
            if abs(d) >= abs(c):  # type: ignore
                row[credit_col] = ""
            else:
                row[debit_col] = ""
        elif has_d:
            row[credit_col] = ""
        elif has_c:
            row[debit_col] = ""

    return rows


# ═══════════════════════════════════════════════════════════════════════════
# PUBLIC API: remove_empties
# ═══════════════════════════════════════════════════════════════════════════

def remove_empties(
    rows: List[Dict[str, str]], core_mapping: Dict[str, str]
) -> List[Dict[str, str]]:
    """Remove rows that are 100% empty — has NO data in ANY column."""
    before = len(rows)
    cleaned = []

    for row in rows:
        has_any = any(str(v).strip() for v in row.values())
        if has_any:
            cleaned.append(row)

    removed = before - len(cleaned)
    if removed:
        logger.info("Removed %d truly empty rows", removed)
    return cleaned


# ═══════════════════════════════════════════════════════════════════════════
# PUBLIC API: dedupe
# ═══════════════════════════════════════════════════════════════════════════

def dedupe(
    rows: List[Dict[str, str]], core_mapping: Dict[str, str] = {}
) -> List[Dict[str, str]]:
    """Remove exact-duplicate rows (PDF extraction artifacts only)."""
    before = len(rows)
    seen: set = set()
    cleaned = []

    for row in rows:
        key = tuple(sorted(row.items()))
        if key not in seen:
            seen.add(key)
            cleaned.append(row)

    removed = before - len(cleaned)
    if removed:
        logger.info("Removed %d exact duplicate artifacts", removed)
    return cleaned


# ═══════════════════════════════════════════════════════════════════════════
# PUBLIC API: to_dataframe
# ═══════════════════════════════════════════════════════════════════════════

def to_dataframe(
    rows: List[Dict[str, str]], final_columns: List[str]
) -> pd.DataFrame:
    """Convert row dicts to DataFrame with exact PDF column order."""
    if not rows:
        return pd.DataFrame(columns=final_columns)
    df = pd.DataFrame(rows)
    for col in final_columns:
        if col not in df.columns:
            df[col] = ""
    df = df[final_columns]
    df = df.fillna("")
    return df


# ═══════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _match_column(col_name: str) -> Optional[str]:
    """Match a PDF column header to an internal role using priority matching."""
    s = str(col_name).lower().replace("\n", " ").strip()

    # Exact match (highest confidence)
    for role, keywords in _COL_PATTERNS.items():
        if s in keywords:
            return role

    # Substring match (ordered by priority)
    for role, keywords in _COL_PATTERNS.items():
        for kw in keywords:
            if kw in s:
                return role

    return None


def _parse_num(value: object) -> Optional[float]:
    """Parse monetary string to float. Returns None for empty/invalid."""
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() in ("", "none", "nan", "-", "--", "na", "n/a"):
        return None

    # Remove PNB/SBI Cr./Dr. suffix
    s = _BAL_SUFFIX_RE.sub("", s).strip()

    # Remove commas and currency symbols
    s = s.replace(",", "").replace("₹", "").replace("INR", "").strip()

    # Handle parenthetical negatives: (100.00) → -100.00
    is_neg = False
    if s.startswith("(") and s.endswith(")"):
        is_neg = True
        s = s[1:-1]

    # Remove any remaining alpha except the decimal dot and minus
    s_clean = re.sub(r"[^\d.\-]", "", s)

    if s_clean.startswith("-"):
        is_neg = True
        s_clean = s_clean[1:]
    elif s_clean.endswith("-"):
        is_neg = True
        s_clean = s_clean[:-1]

    try:
        if not s_clean or s_clean == "-":
            return None
        val = abs(float(s_clean))
        return -val if is_neg else val
    except ValueError:
        return None
