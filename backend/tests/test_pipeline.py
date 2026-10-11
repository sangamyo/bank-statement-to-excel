"""
Unit tests for the production pipeline.

Tests cover:
  - Universal spatial parser import / functions
  - Merger: date detection, continuation merge, DR/CR, column locking, reference, zero loss
  - Bank detector: IFSC / header keyword priority
  - Excel generator: 3-sheet interface
  - Full import chain
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.merger import merge_rows, _stitch


# ── Helpers ──

CORE_MAPPING = {
    "Date": "Date",
    "Description": "Narration",
    "Reference": "Chq No",
    "Debit": "Withdrawal",
    "Credit": "Deposit",
    "Balance": "Closing Balance",
}

FINAL_COLUMNS = ["Date", "Narration", "Chq No", "Withdrawal", "Deposit", "Closing Balance"]


def _row(date="", narr="", chq="", wd="", dep="", bal=""):
    return {
        "Date": date,
        "Narration": narr,
        "Chq No": chq,
        "Withdrawal": wd,
        "Deposit": dep,
        "Closing Balance": bal,
    }


# ── Test 1: Date formats ──

def test_date_formats():
    """4 different Indian bank date formats → 4 separate transactions."""
    rows = [
        _row(date="15/10/2025", narr="UPI TRANSFER", wd="500.00", bal="10000.00"),
        _row(date="16-Oct-2025", narr="NEFT CREDIT", dep="1000.00", bal="11000.00"),
        _row(date="17 Oct 2025", narr="ATM WITHDRAWAL", wd="2000.00", bal="9000.00"),
        _row(date="2025-10-18", narr="SALARY", dep="50000.00", bal="59000.00"),
    ]
    merged = merge_rows(rows, CORE_MAPPING, FINAL_COLUMNS)
    assert len(merged) == 4, f"Expected 4, got {len(merged)}"
    print("  ✓ test_date_formats")


# ── Test 2: Multi-line merge ──

def test_multiline_merge():
    """Continuation rows merge into previous description."""
    rows = [
        _row(date="15/10/2025", narr="UPI-MANOJ", wd="7000.00", bal="10000.00"),
        _row(narr="KUMAR-DR-REF123456789012"),
        _row(narr="ADDITIONAL DETAILS"),
        _row(date="16/10/2025", narr="SALARY CREDIT", dep="50000.00", bal="60000.00"),
    ]
    merged = merge_rows(rows, CORE_MAPPING, FINAL_COLUMNS)
    assert len(merged) == 2, f"Expected 2, got {len(merged)}"
    desc = merged[0]["Narration"]
    assert "UPI-MANOJ" in desc
    assert "KUMAR" in desc
    assert "ADDITIONAL DETAILS" in desc
    print("  ✓ test_multiline_merge")


# ── Test 3: DR/CR binding ──

def test_dr_cr_binding():
    """'7000.00 DR' → Debit=7000.00, Credit=empty."""
    rows = [
        _row(date="15/10/2025", narr="PURCHASE", dep="7000.00 DR", bal="3000.00"),
    ]
    merged = merge_rows(rows, CORE_MAPPING, FINAL_COLUMNS)
    assert len(merged) == 1
    txn = merged[0]
    assert txn["Withdrawal"].strip() != "", f"Debit should be populated"
    assert txn["Deposit"].strip() == "", f"Credit should be empty, got '{txn['Deposit']}'"
    print("  ✓ test_dr_cr_binding")


# ── Test 4: Column locking ──

def test_column_locking():
    """Once set, amounts are NOT overwritten by continuation rows."""
    rows = [
        _row(date="15/10/2025", narr="ORIGINAL", wd="500.00", bal="10000.00"),
        _row(wd="999.00", bal="9500.00"),
    ]
    merged = merge_rows(rows, CORE_MAPPING, FINAL_COLUMNS)
    assert len(merged) == 1
    assert merged[0]["Withdrawal"] == "500.00", f"Got '{merged[0]['Withdrawal']}'"
    assert merged[0]["Closing Balance"] == "9500.00", f"Got '{merged[0]['Closing Balance']}'"
    print("  ✓ test_column_locking")


# ── Test 5: Reference extraction ──

def test_reference_extraction():
    """10+ digit numbers extracted from block text."""
    rows = [
        _row(date="15/10/2025", narr="UPI TRANSFER", wd="500.00", bal="10000.00"),
        _row(narr="REF 1234567890123"),
    ]
    merged = merge_rows(rows, CORE_MAPPING, FINAL_COLUMNS)
    assert len(merged) == 1
    assert merged[0]["Chq No"] == "1234567890123"
    print("  ✓ test_reference_extraction")


# ── Test 6: Wrapped reference is stitched, not truncated ──

def test_reference_stitching():
    rows = [
        _row(date="15/10/2025", narr="NEFT", chq="ABCD12345", wd="10.00", bal="90.00"),
        _row(chq="6789"),
    ]
    merged = merge_rows(rows, CORE_MAPPING, FINAL_COLUMNS)
    assert len(merged) == 1
    assert merged[0]["Chq No"] == "ABCD123456789", merged[0]["Chq No"]
    print("  ✓ test_reference_stitching")


# ── Test 6b: Bank detection priority ──

def test_bank_detection():
    from services.bank_detector import detect_bank_from_text
    # IFSC prefix in header wins over a counterparty name
    assert detect_bank_from_text("Account statement\nIFSC: SBIN0001234\nNEFT to HDFC") == "sbi"
    assert detect_bank_from_text("Axis Bank statement of account") == "axis"
    assert detect_bank_from_text("Generic statement") == "unknown"
    print("  ✓ test_bank_detection")


# ── Test 6c: Header guard rejects transaction lines ──

def test_header_guard():
    from parsers.universal_spatial import _looks_like_header
    words = [{"text": t} for t in ("Date", "Narration", "Withdrawal", "Deposit", "Balance")]
    assert _looks_like_header(words, "date narration withdrawal deposit balance")
    txn = [{"text": t} for t in ("01/04/24", "UPI transfer credit", "100.00")]
    assert not _looks_like_header(txn, "01/04/24 upi transfer credit 100.00")
    print("  ✓ test_header_guard")


# ── Test 7: Smart stitch ──

def test_smart_stitch():
    assert _stitch("UPI-MANOJ", "KUMAR") == "UPI-MANOJKUMAR"
    assert _stitch("123456", "789012") == "123456789012"
    assert _stitch("HELLO", "WORLD") == "HELLO WORLD"
    assert _stitch("PATH/", "TO") == "PATH/TO"
    print("  ✓ test_smart_stitch")


# ── Test 8: Zero data loss (empty block kept) ──

def test_zero_data_loss():
    """Even rows with partial data are preserved."""
    rows = [
        _row(narr="ORPHAN ROW WITH NO DATE"),
    ]
    merged = merge_rows(rows, CORE_MAPPING, FINAL_COLUMNS)
    assert len(merged) == 1, f"Expected 1 (zero loss), got {len(merged)}"
    assert "ORPHAN ROW" in merged[0]["Narration"]
    print("  ✓ test_zero_data_loss")


# ── Test 9: Full import chain ──

def test_import_chain():
    from parsers.universal_spatial import extract, extract_with_raw, extract_raw_lines  # noqa: F401
    from services.parser_service import process  # noqa: F401
    from services.excel_generator import generate_excel  # noqa: F401
    from services.bank_detector import detect_bank, detect_bank_from_text  # noqa: F401
    from services.validator import validate  # noqa: F401
    import app  # noqa: F401
    print("  ✓ test_import_chain")


# ── Test 10: Excel generator accepts 3-sheet params ──

def test_excel_generator_signature():
    import inspect
    from services.excel_generator import generate_excel
    sig = inspect.signature(generate_excel)
    params = list(sig.parameters.keys())
    assert "raw_lines" in params, f"Missing 'raw_lines' param: {params}"
    assert "bank_name" in params, f"Missing 'bank_name' param: {params}"
    print("  ✓ test_excel_generator_signature")


# ── Runner ──

if __name__ == "__main__":
    print("\n🧪 Running production pipeline tests...\n")

    tests = [
        test_date_formats,
        test_multiline_merge,
        test_dr_cr_binding,
        test_column_locking,
        test_reference_extraction,
        test_reference_stitching,
        test_bank_detection,
        test_header_guard,
        test_smart_stitch,
        test_zero_data_loss,
        test_import_chain,
        test_excel_generator_signature,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"  ✘ {test.__name__} FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"  ✘ {test.__name__} ERROR: {e}")
            failed += 1

    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)} tests")
    if failed == 0:
        print("✅ All tests passed!")
    else:
        print("❌ Some tests failed!")
    print(f"{'='*50}\n")
