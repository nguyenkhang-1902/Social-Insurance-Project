import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT_DIR / "Code"))

from database import engine, init_db
from models import Employee, PayrollHistory

DATA_DIR = ROOT_DIR / "Templates"

MASTER_FILE_CANDIDATES = [
    DATA_DIR / "DANH SÁCH THEO DÕI QUÁ TRÌNH THAM GIA BẢO HIỂM THẤT NGHIỆP.csv",
    DATA_DIR / "DANH SÁCH THEO DÕI QUÁ TRÌNH THAM GIA BẢO HIỂM THẤT NGHIỆP.xlsx",
    DATA_DIR / "DANH SÁCH THEO DÕI QUÁ TRÌNH THAM GIA BẢO HIỂM THẤT NGHIỆP - 1.xlsx",
    DATA_DIR / "DANH SÁCH THEO DOI QUA TRINH THAM GIA BAO HIEM THAT NGHIEP - 1.xlsx",
]


def parse_date_series(series: pd.Series) -> pd.Series:
    """Parse date series with proper handling of invalid dates.
    
    Returns parsed dates or None for invalid/empty values.
    Explicitly filters out 1970-01-01 dates (often from invalid parsing).
    """
    parsed = pd.to_datetime(series, dayfirst=True, errors="coerce")
    result = []
    for val in parsed:
        if pd.isna(val):
            result.append(None)
        else:
            date_val = val.date()
            # Filter out 1970-01-01 which indicates an invalid/empty date
            if date_val.year == 1970 and date_val.month == 1 and date_val.day == 1:
                result.append(None)
            else:
                result.append(date_val)
    return pd.Series(result, dtype=object)


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


def normalize_date_value(value: object) -> Optional[object]:
    if value is None:
        return None
    if pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime().date()
    if isinstance(value, datetime):
        return value.date()
    if hasattr(value, "to_pydatetime"):
        try:
            return value.to_pydatetime().date()
        except Exception:
            return None
    if getattr(value, "__class__", None) is not None and value.__class__.__name__ == "NaTType":
        return None
    if isinstance(value, float) and (value != value or abs(value) == float("inf")):
        return None
    return value


def normalize_text_value(value: object) -> Optional[str]:
    if value is None:
        return None
    if pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def normalize_status_string(value: object) -> Optional[str]:
    text = normalize_text_value(value)
    if text is None:
        return None
    normalized = text.upper()
    if normalized in {"RESIGNATION", "RESIGNED"}:
        return "NV"
    return normalized


def parse_salary_value(value: object) -> Optional[float]:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null", "n/a", "na"}:
        return None

    upper_text = text.upper()
    if upper_text in {"TS", "OM", "KL", "ST", "NV"}:
        return 0.0

    cleaned = text.replace(",", "").replace(" ", "")
    if re.fullmatch(r"-?\d+(\.\d+)?", cleaned):
        numeric_value = float(cleaned)  
        return int(numeric_value) if numeric_value.is_integer() else numeric_value
    return None


def normalize_db_value(value: object, default=None):
    if value is None:
        return default
    if pd.isna(value):
        return default
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.to_pydatetime().date() if isinstance(value, pd.Timestamp) else value.date()
    if hasattr(value, "to_pydatetime"):
        try:
            return value.to_pydatetime().date()
        except Exception:
            return default
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if isinstance(value, float) and (value != value or abs(value) == float("inf")):
            return default
    if isinstance(value, (int, float, str)):
        return value
    return value


def find_master_file(data_dir: Path) -> Path:
    for candidate in MASTER_FILE_CANDIDATES:
        if candidate.exists():
            return candidate

    workbook_candidates = sorted(data_dir.glob("*.csv")) + sorted(data_dir.glob("*.xlsx"))
    for candidate in workbook_candidates:
        lowered = candidate.name.lower()
        if "theo" in lowered and ("bao" in lowered or "bhtn" in lowered or "that" in lowered):
            return candidate

    raise FileNotFoundError(f"Cannot find the master insurance history workbook in {data_dir}")


def load_master_history_dataframe(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        raw = pd.read_csv(path, header=None)
    else:
        raw = pd.read_excel(path, sheet_name=0, header=None)
    if raw.empty:
        raise ValueError("Master workbook is empty")

    month_row_idx = None
    for idx in range(raw.shape[0]):
        row = raw.iloc[idx]
        if row.apply(lambda value: isinstance(value, (datetime, pd.Timestamp))).sum() >= 12:
            month_row_idx = idx
            break

    if month_row_idx is None:
        raise ValueError("Unable to find the month header row in the master workbook")

    date_columns = [
        idx for idx, value in enumerate(raw.iloc[month_row_idx])
        if isinstance(value, (datetime, pd.Timestamp))
    ]
    if not date_columns:
        raise ValueError("No monthly columns were found in the master workbook")

    month_start_col = date_columns[0]
    month_dates = [pd.to_datetime(raw.iloc[month_row_idx, idx]).normalize() for idx in date_columns]

    data_start_idx = month_row_idx + 1
    for idx in range(data_start_idx, raw.shape[0]):
        first_value = raw.iloc[idx, 1] if raw.shape[1] > 1 else None
        if pd.notna(first_value) and str(first_value).strip():
            data_start_idx = idx
            break

    data_frame = raw.iloc[data_start_idx:].copy()
    if data_frame.empty:
        raise ValueError("No employee rows were found in the master workbook")

    metadata_columns = data_frame.iloc[:, :month_start_col].copy()
    metadata_columns = metadata_columns.iloc[:, :7]
    metadata_columns.columns = ["stt", "emp_id", "full_name", "join_date", "birth_date", "social_no", "social_date"]

    month_columns = data_frame.iloc[:, month_start_col:].copy()
    month_columns.columns = month_dates

    wide_frame = pd.concat([metadata_columns.reset_index(drop=True), month_columns.reset_index(drop=True)], axis=1)
    long_frame = wide_frame.melt(
        id_vars=list(metadata_columns.columns),
        var_name="month",
        value_name="raw_value",
    )

    # Preserve leading zeros in emp_id by converting to string first
    long_frame["emp_id"] = long_frame["emp_id"].astype(str).str.strip().replace({"nan": None, "None": None})
    long_frame = long_frame.dropna(subset=["emp_id"])
    long_frame["full_name"] = long_frame["full_name"].astype(str).str.strip().replace({"nan": None, "None": None})
    long_frame["join_date"] = parse_date_series(long_frame.get("join_date", pd.Series(dtype="object")))
    long_frame["birth_date"] = parse_date_series(long_frame.get("birth_date", pd.Series(dtype="object")))
    long_frame["social_no"] = long_frame.get("social_no", pd.Series([None] * len(long_frame), dtype=object)).astype(str).str.strip().replace({"nan": None, "None": None})
    
    # PHASE 25: Read social_date as pure string and clean rigorously
    # This prevents Excel's automatic date conversion from creating 1970 dates
    social_date_raw = long_frame.get("social_date", pd.Series(dtype="object"))
    long_frame["social_date"] = social_date_raw.apply(clean_social_date_string)
    long_frame["month"] = pd.to_datetime(long_frame["month"], errors="coerce")
    long_frame["record_month"] = long_frame["month"].dt.month
    long_frame["record_year"] = long_frame["month"].dt.year
    long_frame = long_frame.sort_values(["emp_id", "month"]).reset_index(drop=True)

    return long_frame


def build_history_records(long_frame: pd.DataFrame) -> tuple[list[Employee], list[PayrollHistory]]:
    long_frame = long_frame.copy()
    long_frame["raw_text"] = long_frame["raw_value"].astype(str).str.strip().replace({"nan": None, "None": None, "<NA>": None})
    long_frame["raw_text_upper"] = long_frame["raw_text"].str.upper()

    long_frame["status"] = None
    long_frame["salary_value"] = None
    for idx, row in long_frame.iterrows():
        raw_text = row.get("raw_text_upper")
        raw_value = row.get("raw_value")
        if raw_text is None or str(raw_text).strip() == "":
            long_frame.at[idx, "status"] = "Active"
            long_frame.at[idx, "salary_value"] = None
            continue

        status_value = normalize_status_string(raw_value)
        if status_value in {"TS", "OM", "KL", "ST", "NV"}:
            long_frame.at[idx, "status"] = status_value
            long_frame.at[idx, "salary_value"] = 0.0
            continue

        numeric_value = parse_salary_value(raw_value)
        if numeric_value is not None:
            long_frame.at[idx, "status"] = "Active"
            long_frame.at[idx, "salary_value"] = numeric_value
        else:
            long_frame.at[idx, "status"] = "Active"
            long_frame.at[idx, "salary_value"] = None

    long_frame["is_salary"] = long_frame["salary_value"].notna()
    long_frame["has_value"] = long_frame["raw_text"].notna() & long_frame["raw_text"].ne("")

    long_frame = long_frame.sort_values(["emp_id", "month"], kind="mergesort").reset_index(drop=True)
    long_frame["prior_has_value"] = long_frame.groupby("emp_id")["has_value"].shift(1).fillna(False)
    long_frame["prior_status"] = long_frame.groupby("emp_id")["status"].shift(1)
    long_frame["current_blank"] = ~long_frame["has_value"]

    keep_mask = pd.Series(False, index=long_frame.index)
    drop_mask = pd.Series(False, index=long_frame.index)
    for emp_id, emp_frame in long_frame.groupby("emp_id", sort=False):
        saw_valid_value = False
        blank_run_indices = []
        for row_idx, row in emp_frame.iterrows():
            if row["has_value"]:
                saw_valid_value = True
                if blank_run_indices:
                    # A new valid value ended the blank run; keep the last blank row as resignation and drop earlier blanks.
                    last_blank_idx = blank_run_indices[-1]
                    keep_mask.loc[emp_frame.index[last_blank_idx]] = True
                    for idx in blank_run_indices[:-1]:
                        drop_mask.loc[emp_frame.index[idx]] = True
                    blank_run_indices = []
                continue

            if saw_valid_value:
                blank_run_indices.append(row_idx)
            else:
                drop_mask.loc[emp_frame.index[row_idx]] = True

        if blank_run_indices:
            last_blank_idx = blank_run_indices[-1]
            keep_mask.loc[emp_frame.index[last_blank_idx]] = True
            for idx in blank_run_indices[:-1]:
                drop_mask.loc[emp_frame.index[idx]] = True

    long_frame.loc[keep_mask & long_frame["current_blank"], "status"] = "NV"
    long_frame.loc[keep_mask & long_frame["current_blank"], "resign_date"] = long_frame.loc[keep_mask & long_frame["current_blank"], "month"].dt.date
    long_frame = long_frame.loc[~drop_mask].copy()

    if long_frame.empty:
        return [], []

    long_frame = long_frame.sort_values(["emp_id", "month"], kind="mergesort").reset_index(drop=True)
    long_frame["base_salary"] = long_frame.groupby("emp_id")["salary_value"].ffill()
    long_frame["base_salary"] = long_frame["base_salary"].fillna(0.0)
    long_frame["bhtn_val"] = long_frame["raw_value"].apply(lambda value: None if pd.isna(value) else str(value))
    long_frame["status_in_month"] = long_frame["status"].fillna("Active")
    long_frame["status_in_month"] = long_frame["status_in_month"].replace({"None": "Active", "NV": "Resigned"})
    long_frame["resign_date"] = pd.to_datetime(long_frame.get("resign_date"), errors="coerce").dt.date
    long_frame = long_frame.drop_duplicates(subset=["emp_id", "record_year", "record_month"], keep="last").reset_index(drop=True)

    employee_base = (
        long_frame[["emp_id", "full_name", "join_date", "birth_date", "social_no", "social_date"]]
        .drop_duplicates(subset=["emp_id"])
        .copy()
    )
    employee_base = employee_base.dropna(subset=["emp_id"])

    latest_history = (
        long_frame.sort_values(["emp_id", "record_year", "record_month"], kind="mergesort")
        .drop_duplicates(subset=["emp_id"], keep="last")
        .reset_index(drop=True)
    )

    employee_rows = employee_base.merge(
        latest_history[["emp_id", "status", "base_salary", "resign_date"]],
        on="emp_id",
        how="left",
    )
    employee_rows["current_status"] = employee_rows["status"].fillna("Active")
    employee_rows["current_status"] = employee_rows["current_status"].replace({"None": "Active"})
    employee_rows["current_status"] = employee_rows["current_status"].replace({"NV": "Resigned"})
    resignation_emp_ids = set(long_frame.loc[long_frame["status"].eq("NV"), "emp_id"].dropna().astype(str))
    employee_rows.loc[employee_rows["emp_id"].isin(resignation_emp_ids), "current_status"] = "Resigned"
    employee_rows["current_salary"] = employee_rows["base_salary"].fillna(0.0)
    employee_rows["resign_date"] = pd.to_datetime(employee_rows["resign_date"], errors="coerce").dt.date

    employee_records = []
    for _, row in employee_rows.iterrows():
        salary_value = row.get("current_salary", 0.0)
        if pd.isna(salary_value):
            salary_value = 0.0
        
        # PHASE 25: social_date is now a clean string (or None), not a date object
        social_date_val = row.get("social_date")
        if social_date_val is None or pd.isna(social_date_val):
            social_date_val = None
        else:
            social_date_val = str(social_date_val).strip() or None
        
        employee_records.append(
            Employee(
                emp_id=normalize_db_value(str(row["emp_id"]), "Unknown"),
                full_name=normalize_db_value(normalize_text_value(row.get("full_name")), "Unknown") or "Unknown",
                join_date=normalize_db_value(normalize_date_value(row.get("join_date"))),
                birth_date=normalize_db_value(normalize_date_value(row.get("birth_date"))),
                social_no=normalize_db_value(normalize_text_value(row.get("social_no"))),
                social_date=social_date_val,
                current_status=normalize_db_value(normalize_text_value(row.get("current_status")), "Active") or "Active",
                current_salary=float(normalize_db_value(salary_value, 0.0) or 0.0),
                resign_date=normalize_db_value(normalize_date_value(row.get("resign_date"))),
            )
        )

    history_records = []
    for _, row in long_frame.iterrows():
        salary_value = row.get("base_salary", 0.0)
        if pd.isna(salary_value):
            salary_value = 0.0
        history_records.append(
            PayrollHistory(
                emp_id=normalize_db_value(str(row["emp_id"]), "Unknown"),
                record_month=int(normalize_db_value(row["record_month"], 0) or 0),
                record_year=int(normalize_db_value(row["record_year"], 0) or 0),
                base_salary=float(normalize_db_value(salary_value, 0.0) or 0.0),
                status_in_month=normalize_db_value(normalize_text_value(row.get("status_in_month")), "Active") or "Active",
                resign_date=normalize_db_value(normalize_date_value(row.get("resign_date"))),
                bhxh_val=None,
                bhyt_val=None,
                bhtn_val=normalize_db_value(normalize_text_value(row.get("bhtn_val"))),
                bhbnn_val=None,
            )
        )

    return employee_records, history_records


def apply_backward_salary_correction() -> int:
    with Session(engine) as session:
        histories = session.query(PayrollHistory).order_by(PayrollHistory.emp_id, PayrollHistory.record_year, PayrollHistory.record_month).all()
        history_by_emp = {}
        for history in histories:
            history_by_emp.setdefault(history.emp_id, []).append(history)

        updated = 0
        for emp_id, rows in history_by_emp.items():
            for idx, history in enumerate(rows):
                if history.status_in_month in {"Active", "TS", "OM", "KL", "ST", "NV", "RESIGNATION"}:
                    continue
                if history.base_salary and history.base_salary > 0:
                    continue
                if idx == 0:
                    continue
                previous_history = rows[idx - 1]
                if previous_history.base_salary and previous_history.base_salary > 0:
                    history.status_in_month = "NV"
                    session.add(history)
                    updated += 1
        session.commit()
        return updated


def seed_database() -> None:
    init_db()
    master_path = find_master_file(DATA_DIR)
    print(f"Loading master workbook from {master_path}")

    long_frame = load_master_history_dataframe(master_path)
    employee_records, history_records = build_history_records(long_frame)

    try:
        with Session(engine) as session:
            session.execute(text("DELETE FROM payroll_history"))
            session.execute(text("DELETE FROM employee"))
            session.commit()

            if employee_records:
                for start in range(0, len(employee_records), 5000):
                    session.bulk_save_objects(employee_records[start : start + 5000])
            if history_records:
                for start in range(0, len(history_records), 10000):
                    session.bulk_save_objects(history_records[start : start + 10000])
            session.commit()

        corrected = apply_backward_salary_correction()
        print(f"Database seed completed successfully. Employees: {len(employee_records)}, History: {len(history_records)}, Backward corrected rows: {corrected}")
    except Exception as exc:
        print(f"Database seed failed: {exc}")
        raise


if __name__ == "__main__":
    try:
        seed_database()
    except Exception as exc:
        print(f"Seed script error: {exc}")
        sys.exit(1)
