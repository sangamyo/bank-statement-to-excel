"""
Bank Detector — identifies the issuing bank from PDF text.

Strategy (most to least reliable):
  1. IFSC code prefix in the statement header (e.g. HDFC0001234 → HDFC).
  2. Earliest bank-name mention in the statement header.
  3. Any bank-name mention in the first pages (legacy keyword scan).

Only the header (start of page 1) is used for steps 1-2 so that counterparty
names in transactions ("NEFT to HDFC ...") do not cause misdetection.
Returns a lowercase key such as "hdfc", "icici", "sbi", "kotak", "axis",
"pnb", or "unknown".
"""

import re
from typing import Dict, List

import pdfplumber  # type: ignore

from utils.logger import get_logger

logger = get_logger("bank_detector")

HEADER_CHARS = 2000

IFSC_PREFIXES: Dict[str, str] = {
    "HDFC": "hdfc",
    "ICIC": "icici",
    "SBIN": "sbi",
    "KKBK": "kotak",
    "UTIB": "axis",
    "PUNB": "pnb",
    "BARB": "bob",
    "CNRB": "canara",
    "UBIN": "union",
    "IDIB": "indian",
    "YESB": "yes",
    "INDB": "indusind",
    "IDFB": "idfc",
    "AUBL": "au",
}

BANK_KEYWORDS: Dict[str, List[str]] = {
    "hdfc": ["hdfc bank", "hdfc"],
    "icici": ["icici bank", "icici"],
    "sbi": ["state bank of india", "sbi"],
    "kotak": ["kotak mahindra", "kotak"],
    "axis": ["axis bank", "axis"],
    "pnb": ["punjab national bank", "pnb"],
}

_IFSC_RE = re.compile(r"\b([A-Z]{4})0[A-Z0-9]{6}\b")


def detect_bank_from_text(text: str) -> str:
    """Detect the bank from already-extracted statement text."""
    header = text[:HEADER_CHARS]

    # 1. IFSC prefix in header — strongest signal
    for m in _IFSC_RE.finditer(header.upper()):
        bank = IFSC_PREFIXES.get(m.group(1))
        if bank:
            logger.info("Bank detected: %s (IFSC prefix)", bank.upper())
            return bank

    # 2. Earliest bank-name mention in header
    lowered = header.lower()
    best_bank, best_pos = None, len(lowered) + 1
    for bank, keywords in BANK_KEYWORDS.items():
        for kw in keywords:
            m = re.search(r"\b" + re.escape(kw) + r"\b", lowered)
            if m and m.start() < best_pos:
                best_bank, best_pos = bank, m.start()
    if best_bank:
        logger.info("Bank detected: %s (header keyword)", best_bank.upper())
        return best_bank

    # 3. Legacy scan of the whole provided text
    lowered_all = text.lower()
    for bank, keywords in BANK_KEYWORDS.items():
        for kw in keywords:
            if kw in lowered_all:
                logger.info("Bank detected: %s (matched '%s')", bank.upper(), kw)
                return bank

    logger.warning("Could not identify bank — using generic parsing")
    return "unknown"


def detect_bank(pdf_path: str, max_pages: int = 3) -> str:
    """Scan the first `max_pages` pages of a PDF and detect the bank."""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            text = "\n".join(
                str(page.extract_text() or "") for page in pdf.pages[:max_pages]
            )
    except Exception as e:
        logger.error("Cannot read PDF for bank detection: %s", e)
        return "unknown"
    return detect_bank_from_text(text)
