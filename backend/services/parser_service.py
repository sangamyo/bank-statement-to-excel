"""
Parser Service — Production Pipeline Orchestrator
===================================================

Full pipeline:
  1. Extract via UNIVERSAL SPATIAL PARSER (primary, single PDF pass that also
     collects the raw text lines) → fallback: generic table extraction
  2. Detect bank (IFSC prefix / header keywords)
  3. Map columns DYNAMICALLY from PDF header (no hardcoding)
  4. Remove junk rows (page headers, footers, legends)
  5. Merge multi-line transactions (date-at-start grouping)
  6. Parse dates
  7. Coerce numerics
  8. Enforce Debit/Credit mutex
  9. Remove truly empty rows
  10. Validate (balance continuity)
  11. Export 3-sheet Excel

STRICT RULES:
  - Column names are PRESERVED exactly as found in the PDF
  - Column order is PRESERVED exactly as found in the PDF
  - ZERO rows are dropped — invalid rows merge into previous description
"""

from __future__ import annotations

from typing import Optional, Tuple

import pandas as pd

from services.bank_detector import detect_bank_from_text
from services.merger import merge_rows
from services.cleaner import (
    map_columns, remove_junk, parse_dates,
    coerce_numerics, enforce_mutex, remove_empties,
    dedupe, to_dataframe,
)
from services.validator import validate, apply_validation_rules
from services.excel_generator import generate_excel

from parsers.universal_spatial import extract_with_raw, extract_raw_lines
from parsers.fallback_parser import extract as fallback_extract

from utils.logger import get_logger

logger = get_logger("parser_service")


def process(
    pdf_path: str,
    file_id: str,
    original_filename: str,
    output_dir: Optional[str] = None,
) -> Tuple[str, pd.DataFrame]:
    """
    Full pipeline: PDF → extract → detect → merge → clean → validate → Excel.

    Returns (excel_path, cleaned_dataframe).
    Raises ValueError if extraction yields zero usable data.
    """
    logger.info("━" * 64)
    logger.info("PIPELINE START: %s", file_id)
    logger.info("━" * 64)

    # ═══ Step 1: Extract via UNIVERSAL SPATIAL PARSER (+ raw lines) ═══
    header, raw_rows, raw_lines = extract_with_raw(pdf_path)
    parser_name = "UNIVERSAL_SPATIAL"

    if not raw_rows:
        logger.warning("Universal spatial returned 0 rows — trying fallback")
        header, raw_rows = fallback_extract(pdf_path)
        parser_name = "FALLBACK"

    # ═══ Step 2: Detect bank from the statement header ═══
    if not raw_lines:
        raw_lines = extract_raw_lines(pdf_path)
    bank = detect_bank_from_text("\n".join(raw_lines[:150]))

    raw_count = len(raw_rows)
    logger.info("Parser: %s → %d raw rows, header=%s",
                parser_name, raw_count, header[:8] if header else None)

    if raw_count == 0:
        raise ValueError(
            "No data extracted from PDF. The file may not contain tabular data "
            "or may be a scanned image requiring OCR."
        )

    # ═══ Step 4: Map columns DYNAMICALLY ═══
    # map_columns detects column roles from the header names
    # but PRESERVES the original column names in the output
    row_dicts, core_mapping, final_columns = map_columns(header, raw_rows)
    logger.info("TRACE [map_columns]: %d → %d rows | columns=%s | mapping=%s",
                raw_count, len(row_dicts), final_columns, core_mapping)

    # ═══ Step 5: Remove junk ═══
    before = len(row_dicts)
    row_dicts = remove_junk(row_dicts, core_mapping)
    logger.info("TRACE [remove_junk]: %d → %d (-%d)", before, len(row_dicts), before - len(row_dicts))

    # ═══ Step 6: Merge multi-line transactions ═══
    before = len(row_dicts)
    row_dicts = merge_rows(row_dicts, core_mapping, final_columns)
    merged_count = len(row_dicts)
    logger.info("TRACE [merge_rows]: %d → %d", before, merged_count)

    # ═══ Step 7: Parse dates ═══
    row_dicts = parse_dates(row_dicts, core_mapping)

    # ═══ Step 8: Coerce numerics ═══
    row_dicts = coerce_numerics(row_dicts, core_mapping, bank)

    # ═══ Step 9: Debit/Credit mutex ═══
    row_dicts = enforce_mutex(row_dicts, core_mapping, bank)

    # ═══ Step 10: Remove truly empty rows ═══
    before = len(row_dicts)
    row_dicts = remove_empties(row_dicts, core_mapping)
    logger.info("TRACE [remove_empties]: %d → %d (-%d)", before, len(row_dicts), before - len(row_dicts))

    # ═══ Step 11: Dedupe ═══
    before = len(row_dicts)
    row_dicts = dedupe(row_dicts, core_mapping)
    logger.info("TRACE [dedupe]: %d → %d (-%d)", before, len(row_dicts), before - len(row_dicts))

    # ═══ Step 12: Validation rules ═══
    before = len(row_dicts)
    row_dicts = apply_validation_rules(row_dicts, core_mapping, final_columns)
    logger.info("TRACE [validation]: %d → %d", before, len(row_dicts))

    # ═══ Step 13: Convert to DataFrame ═══
    df = to_dataframe(row_dicts, final_columns)

    if df.empty:
        raise ValueError("No valid transactions found after cleaning")

    # ═══ Step 14: Validate balance continuity ═══
    report = validate(df, raw_count, merged_count)

    logger.info(
        "PIPELINE COMPLETE: %d raw → %d merged → %d final (bank=%s)",
        raw_count, merged_count, len(df), bank.upper(),
    )

    # ═══ Step 15: Export 3-SHEET EXCEL ═══
    excel_path = generate_excel(
        dataframes=[df],
        file_id=file_id,
        original_filename=original_filename,
        core_mapping=core_mapping,
        raw_lines=raw_lines,
        bank_name=bank.upper(),
        output_dir=output_dir,
    )

    return excel_path, df
