"""
Fallback Parser — handles any unrecognised bank format.

Uses the generic streaming extractor from services/extractor.py.
This is the safety net that ensures ZERO data loss even for unknown formats.
"""

from typing import List, Optional, Tuple

from services.extractor import extract_all_rows
from utils.logger import get_logger

logger = get_logger("parser.fallback")


def extract(pdf_path: str) -> Tuple[Optional[List[str]], List[List[str]]]:
    """
    Generic extraction using the multi-strategy streaming extractor.
    Returns (header, rows).
    """
    logger.info("Fallback parser: using generic streaming extractor")
    header, rows = extract_all_rows(pdf_path)
    logger.info("Fallback parser: %d raw rows extracted", len(rows))
    return header, rows
