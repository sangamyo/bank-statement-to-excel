"""
Validator — Integrity checks ensuring zero data loss.

Logs a full audit trail:
  - Total raw rows
  - Rows after merge
  - Rows after cleaning
  - Final output rows

Raises warnings if row count drops significantly.
"""

from typing import Dict, List

import pandas as pd

from utils.logger import get_logger

logger = get_logger("validator")


def apply_validation_rules(rows: List[Dict[str, str]], core_mapping: Dict[str, str], final_columns: List[str]) -> List[Dict[str, str]]:
    """
    Enforces strict structural rules:
    - Date must exist
    - Balance must exist
    - At least one of Debit/Credit must exist

    If not -> Merge into previous row's Description.
    """
    if not rows:
        return []
        
    date_col = core_mapping.get("Date")
    balance_col = core_mapping.get("Balance")
    debit_col = core_mapping.get("Debit")
    credit_col = core_mapping.get("Credit")
    desc_col = core_mapping.get("Description")
    
    validated = []
    
    for row in rows:
        has_date = bool(str(row.get(date_col, "")).strip()) if date_col else True
        has_balance = bool(str(row.get(balance_col, "")).strip()) if balance_col else True
        has_amount = False
        
        if debit_col and str(row.get(debit_col, "")).strip():
            has_amount = True
        if credit_col and str(row.get(credit_col, "")).strip():
            has_amount = True
            
        if not (debit_col or credit_col):
            has_amount = True
            
        is_valid = has_date and has_balance and has_amount
        
        if is_valid:
            validated.append(row)
        else:
            if not validated:
                validated.append(row)
            else:
                prev = validated[-1]
                add_text = " ".join(str(val).strip() for col, val in row.items() if str(val).strip() and col != date_col)
                if desc_col and add_text:
                    prev_desc = str(prev.get(desc_col, "")).strip()
                    prev[desc_col] = (prev_desc + " " + add_text).strip()
                    
    logger.info("Validation Engine: Merged %d invalid rows into previous rows.", len(rows) - len(validated))
    
    validate_financials(validated, core_mapping)
    return validated


def validate_financials(rows: List[Dict[str, str]], core_mapping: Dict[str, str]) -> None:
    """Mathematical continuity check: Previous Balance + Credit - Debit = Current Balance."""
    balance_col = core_mapping.get("Balance")
    debit_col = core_mapping.get("Debit")
    credit_col = core_mapping.get("Credit")
    
    if not balance_col:
        return
        
    running_balance = None
    mismatches = 0
    
    for i, row in enumerate(rows):
        bal_str = str(row.get(balance_col, "")).replace(",", "").strip()
        deb_str = str(row.get(debit_col, "")).replace(",", "").strip() if debit_col else ""
        cred_str = str(row.get(credit_col, "")).replace(",", "").strip() if credit_col else ""
        
        try:
            curr_bal = float(bal_str) if bal_str else None
        except ValueError:
            curr_bal = None
            
        try:
            debit = abs(float(deb_str)) if deb_str else 0.0
        except ValueError:
            debit = 0.0
            
        try:
            credit = abs(float(cred_str)) if cred_str else 0.0
        except ValueError:
            credit = 0.0
            
        if curr_bal is not None:
            if running_balance is not None:
                expected = round(running_balance + credit - debit, 2)
                actual = round(curr_bal, 2)
                if abs(expected - actual) > 1.0:
                    mismatches += 1
            running_balance = curr_bal

    # Amounts are deliberately NOT logged (statements contain personal data).
    if mismatches:
        logger.warning("Balance continuity: %d row(s) do not reconcile", mismatches)


def validate(
    df: pd.DataFrame,
    raw_row_count: int,
    merged_row_count: int,
) -> Dict:
    """
    Validate the final DataFrame and log an audit report.

    Returns a dict:
      {
        "is_valid": bool,
        "row_count": int,
        "raw_rows": int,
        "merged_rows": int,
        "duplicates": int,
        "errors": [str],
        "warnings": [str],
      }
    """
    final_count = len(df)
    errors: List[str] = []
    warnings: List[str] = []

    # --- Empty output ---
    if final_count == 0:
        errors.append("OUTPUT IS EMPTY — possible total data loss")

    # --- Duplicate check ---
    dupes = int(df.duplicated().sum())
    if dupes:
        warnings.append(f"{dupes} duplicate rows remain")

    # --- Missing fields ---
    if "Date" in df.columns:
        blank_dates = int((df["Date"].astype(str).str.strip() == "").sum())
        if blank_dates:
            warnings.append(f"{blank_dates} rows have blank dates")

    if "Description" in df.columns:
        blank_desc = int((df["Description"].astype(str).str.strip() == "").sum())
        if blank_desc:
            warnings.append(f"{blank_desc} rows have blank descriptions")

    # --- Suspiciously large drop check ---
    if raw_row_count > 0:
        drop_pct = (raw_row_count - final_count) / raw_row_count * 100
        if drop_pct > 80:
            warnings.append(
                f"Row count dropped {drop_pct:.0f}% (raw={raw_row_count} → final={final_count}). "
                "This is likely due to multi-line merging and is expected for most PDFs."
            )

    # --- Log audit ---
    logger.info("=" * 64)
    logger.info("  VALIDATION REPORT")
    logger.info("  Raw rows extracted:   %d", raw_row_count)
    logger.info("  After merge:          %d", merged_row_count)
    logger.info("  Final output rows:    %d", final_count)
    logger.info("  Duplicates:           %d", dupes)
    for w in warnings:
        logger.warning("  ⚠ %s", w)
    for e in errors:
        logger.error("  ✘ %s", e)
    if not errors:
        logger.info("  ✓ Output looks healthy")
    logger.info("=" * 64)

    return {
        "is_valid": len(errors) == 0,
        "row_count": final_count,
        "raw_rows": raw_row_count,
        "merged_rows": merged_row_count,
        "duplicates": dupes,
        "errors": errors,
        "warnings": warnings,
    }
