#!/usr/bin/env python3
"""
PHASE 25 TEST: Social Date String Cleaning Logic for seed_data.py

This script demonstrates the new pure-string handling of social_date
which prevents invalid 1970-01-01 dates from being stored in the database.
"""

from datetime import date
import pandas as pd
from typing import Optional

print("=" * 90)
print("PHASE 25: SOCIAL DATE INGESTION - PURE STRING CLEANING LOGIC")
print("=" * 90)
print()

# ============================================================================
# PHASE 25 Function: clean_social_date_string()
# This is the core cleaning function used in seed_data.py
# ============================================================================

def clean_social_date_string(value: object) -> Optional[str]:
    """PHASE 25: Clean social_date by reading as pure string and filtering invalid values.
    
    This function handles the social_date column which may contain:
    - Valid date strings (e.g., '02/04/2026', '2026-04-02')
    - Empty cells
    - NaN/None/null indicators
    - Invalid 1970 dates
    
    Returns:
        - None if the value is invalid, empty, or represents 1970
        - Clean date string if valid (with whitespace stripped)
    """
    # Handle None and NaN
    if value is None or pd.isna(value):
        return None
    
    # Convert to string and strip whitespace
    text = str(value).strip()
    
    # Filter empty or invalid marker strings
    if not text or text.lower() in {'nan', 'nat', 'none', '', 'n/a', 'na', '<na>'}:
        return None
    
    # Filter 1970 dates in various formats
    if '1970' in text or '01-01' in text.lower() and len(text) < 15:
        return None
    
    # If we have a non-empty string that's not an invalid marker, keep it
    # This preserves date strings in whatever format they came in
    return text


print("Test Case 1: Invalid/Empty Values")
print("-" * 90)

test_invalid_values = [
    (None, "None (NULL from database)"),
    (pd.NaT, "pandas NaT"),
    ("", "Empty string"),
    ("   ", "Whitespace only"),
    ("nan", "String 'nan'"),
    ("NaN", "String 'NaN'"),
    ("NaT", "String 'NaT'"),
    ("none", "String 'none'"),
    ("n/a", "String 'n/a'"),
]

print("Input -> Output (Expected: all should be None)\n")
for input_val, description in test_invalid_values:
    result = clean_social_date_string(input_val)
    status = "✓" if result is None else "✗"
    print(f"{status} {description:40s} -> {repr(result)}")

print()
print("Test Case 2: Invalid 1970 Dates (Bug Prevention)")
print("-" * 90)

test_1970_dates = [
    ("1970-01-01", "ISO format 1970-01-01"),
    ("01-01-1970", "European format 01-01-1970"),
    ("01/01/1970", "Slash format 01/01/1970"),
    ("1970/01/01", "Alternative 1970/01/01"),
    ("1970", "Just year 1970"),
    (date(1970, 1, 1), "Python date object 1970-01-01"),
]

print("Input -> Output (Expected: all should be None)\n")
for input_val, description in test_1970_dates:
    result = clean_social_date_string(input_val)
    status = "✓" if result is None else "✗"
    print(f"{status} {description:40s} -> {repr(result)}")

print()
print("Test Case 3: Valid Date Strings (Preservation)")
print("-" * 90)

test_valid_dates = [
    ("02/04/2026", "Vietnamese format 02/04/2026"),
    ("2026-04-02", "ISO format 2026-04-02"),
    ("15/03/2020", "European format 15/03/2020"),
    ("2020-03-15", "ISO format 2020-03-15"),
    ("01/01/2022", "Year 2022 with 01-01"),
    ("  2023-05-10  ", "Date with leading/trailing spaces (should be stripped)"),
]

print("Input -> Output (Expected: clean strings preserved)\n")
for input_val, description in test_valid_dates:
    result = clean_social_date_string(input_val)
    status = "✓" if result is not None and isinstance(result, str) else "✗"
    print(f"{status} {description:40s} -> {repr(result)}")

print()
print("Test Case 4: Real-World Scenario - DataFrame Processing")
print("-" * 90)

# Simulate a DataFrame with mixed social_date values from Excel Master file
test_data = {
    'emp_id': ['00001', '00002', '00003', '00004', '00005', '00006', '00007', '00008'],
    'full_name': [
        'Nguyễn Văn A',
        'Trần Thị B', 
        'Phạm Văn C',
        'Hoàng Thị D',
        'Bùi Văn E',
        'Dương Văn F',
        'Lý Văn G',
        'Mai Thị H'
    ],
    'social_date_raw': [
        '1970-01-01',           # Excel bug - incorrect date
        '02/04/2020',           # Valid Vietnamese format
        None,                    # NULL from database
        '',                      # Empty cell
        'NaN',                   # Invalid marker
        '15/03/2023',           # Valid date
        '01/01/1970',           # Another 1970 variant (bug)
        '2022-06-01',           # Valid ISO format
    ]
}

df = pd.DataFrame(test_data)

print("BEFORE cleaning (Raw data from Excel Master):\n")
print(df[['emp_id', 'full_name', 'social_date_raw']].to_string(index=False))

print("\n" + "-" * 90 + "\n")

# Apply cleaning logic
df['social_date_cleaned'] = df['social_date_raw'].apply(clean_social_date_string)

print("AFTER cleaning (What gets stored in SQLite database):\n")
print(df[['emp_id', 'full_name', 'social_date_cleaned']].to_string(index=False))

print("\n" + "=" * 90)
print("PHASE 25 Data Flow Summary:")
print("=" * 90)
print()
print("1. READ from Excel Master file:")
print("   - social_date column may contain: dates, empty cells, '1970' bugs, text noise")
print()
print("2. PARSE with clean_social_date_string():")
print("   - Convert all values to pure STRING")
print("   - Strip whitespace")
print("   - Filter invalid/empty values → None")
print("   - Filter 1970 dates → None")
print("   - Keep valid date strings as-is")
print()
print("3. STORE in SQLite Employee table:")
print("   - Column 'social_date' changed from Date type to String(100)")
print("   - Store None for invalid values")
print("   - Store clean strings for valid dates")
print()
print("4. EXPORT to Excel Reports (3 & 4):")
print("   - Apply _clean_social_date() validation")
print("   - If None or contains '1970' → write empty cell to Excel")
print("   - If valid string → write directly to cell")
print("   - Format: center-aligned, column width 15")
print()
print("=" * 90)
print("✓ PHASE 25 Implementation Complete!")
print("=" * 90)
