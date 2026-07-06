import calendar
import io
import re
import unicodedata
from datetime import date, datetime, time
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_

try:
    from .database import BACKUP_DIR, DATABASE_PATH, backup_database_file, engine, init_db
    from .models import Employee, PayrollHistory
except ImportError:
    from database import BACKUP_DIR, DATABASE_PATH, backup_database_file, engine, init_db
    from models import Employee, PayrollHistory

app = FastAPI(title="HR ETL API")

COLUMN_MAPPING = {
    "STT": "stt",
    "STT\nNo": "stt",
    "Mã NV": "emp_id",
    "MA NV": "emp_id",
    "Emp ID": "emp_id",
    "Mã NV\nEmp ID": "emp_id",
    "Họ và tên": "full_name",
    "Ho ten": "full_name",
    "Full Name": "full_name",
    "Họ và tên\nFull Name": "full_name",
    "Ngày vào": "join_date",
    "Ngay vao": "join_date",
    "Join Date": "join_date",
    "Ngày vào\nJoin Date": "join_date",
    "Ngày sinh": "birth_date",
    "Ngay sinh": "birth_date",
    "Birth Date": "birth_date",
    "Ngày sinh\nBirth Date": "birth_date",
    "Sổ BHXH": "social_no",
    "So BHXH": "social_no",
    "Số BHXH": "social_no",
    "Sổ BHXH\nSocaial No": "social_no",
    "BẮT ĐẦU THAM GIA BHXH TẠI HSV.": "social_date",
    "BẮT ĐẦU THAM GIA BHXH TẠI HSV.\nSTART JOINING SOCIAL INS AT HSV.": "social_date",
    "Ngày tham gia BHXH": "social_date",
    "Social Date": "social_date",
    "Tháng - năm biến động": "month_year_change",
    "Tháng - Năm                     Month - Year": "month_year_change",
    "Tháng": "record_month",
    "Month": "record_month",
    "Năm": "record_year",
    "Year": "record_year",
    "Tình trạng biến động": "status",
    "Tình trạng": "status",
    "Tình trạng                              Status": "status",
    " Tình trạng                              Status": "status",
    "Trạng thái": "status",
    "Status": "status",
    "Ngày nghỉ (End Date)": "resign_date",
    "Ngày nghỉ           Resign Date": "resign_date",
    "End Date": "resign_date",
    "Mức lương mới": "base_salary",
    "Mức lương mới            New Salary": "base_salary",
    "Mức lương mới": "base_salary",
    "Lương đóng bảo hiểm": "base_salary",
    "Salary": "base_salary",
}

STATUS_MAP = {
    "nghỉ việc": "NV",
    "resignation": "NV",
    "resigned": "NV",
    "ts": "TS",
    "om": "OM",
    "kl": "KL",
    "st": "ST",
    "nv": "NV",
}

ROOT_DIR = Path(__file__).resolve().parents[1]
TEMPLATE_FILE = ROOT_DIR / "Templates" / "Code_report.xlsx"

_cached_report_titles: Dict[str, str] = {}


def _normalize_filename_for_export(title: str, month: int, year: int) -> str:
    # ensure Vietnamese D-stroke preserved as 'D' before removing diacritics
    title = title.replace("Đ", "D").replace("đ", "d")
    normalized = unicodedata.normalize("NFKD", title)
    normalized = normalized.encode("ascii", "ignore").decode("ascii")
    normalized = re.sub(r"[^A-Za-z0-9 _-]", "", normalized)
    normalized = re.sub(r"\s+", "_", normalized.strip())
    normalized = re.sub(r"_+", "_", normalized)
    normalized = re.sub(r"(?i)lao_ong", "lao_dong", normalized)
    normalized = re.sub(r"(?i)laoong", "lao_dong", normalized)
    if not normalized:
        normalized = f"report_{month:02d}_{year}"
    # if month and year are not provided (0), keep the legacy placeholder _00_00
    if month == 0 and year == 0:
        suffix = "_00_00"
    else:
        suffix = f"_{month:02d}_{year}"
    return f"{normalized}{suffix}.xlsx"


def _load_report_template_title(sheet_name: str) -> str:
    normalized_sheet = sheet_name.replace(" ", "").lower()
    if normalized_sheet in _cached_report_titles:
        return _cached_report_titles[normalized_sheet]

    if not TEMPLATE_FILE.exists():
        return sheet_name

    try:
        excel = pd.ExcelFile(TEMPLATE_FILE, engine="openpyxl")
        for sheet in excel.sheet_names:
            if sheet.replace(" ", "").lower() == normalized_sheet:
                raw = pd.read_excel(excel, sheet_name=sheet, header=None, nrows=3, engine="openpyxl")
                if raw.shape[0] >= 3:
                    title = raw.iloc[2, 1]
                    if pd.notna(title):
                        cleaned = str(title).strip()
                        _cached_report_titles[normalized_sheet] = cleaned
                        return cleaned
                break
    except Exception:
        pass

    return sheet_name


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    renamed = {}
    for original, normalized in COLUMN_MAPPING.items():
        if original in df.columns:
            renamed[original] = normalized
    df = df.rename(columns=renamed)
    df.columns = df.columns.str.strip()
    return df


def parse_date_column(series: pd.Series) -> pd.Series:
    if series is None:
        return pd.Series([], dtype=object)

    parsed_values = []
    for value in series:
        if pd.isna(value):
            parsed_values.append(None)
            continue

        if isinstance(value, (datetime, date)):
            parsed_values.append(value.date() if isinstance(value, datetime) else value)
            continue

        if isinstance(value, (int, float)) and not isinstance(value, bool):
            try:
                parsed = pd.to_datetime(value, unit="D", origin="1899-12-30", errors="coerce")
                if pd.notna(parsed):
                    parsed_values.append(parsed.date())
                    continue
            except Exception:
                pass

        if isinstance(value, str):
            text = value.strip()
            if not text:
                parsed_values.append(None)
                continue
            if re.fullmatch(r"\d+(?:\.\d+)?", text):
                try:
                    numeric_value = float(text)
                    parsed = pd.to_datetime(numeric_value, unit="D", origin="1899-12-30", errors="coerce")
                    if pd.notna(parsed):
                        parsed_values.append(parsed.date())
                        continue
                except Exception:
                    pass

        try:
            parsed = pd.to_datetime(value, errors="coerce", dayfirst=True)
        except Exception:
            parsed_values.append(None)
            continue

        if pd.isna(parsed):
            parsed_values.append(None)
        else:
            parsed_values.append(parsed.date())
    return pd.Series(parsed_values, dtype=object)


def _stringify_date(value: Optional[date]) -> Optional[str]:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, (datetime, date)):
        return value.strftime("%d-%m-%Y")
    try:
        parsed = pd.to_datetime(value, errors="coerce")
    except Exception:
        return None
    if pd.isna(parsed):
        return None
    return parsed.strftime("%d-%m-%Y")


def _extract_month_year_from_upload(file: UploadFile) -> tuple[Optional[int], Optional[int]]:
    file_content = file.file.read()
    file.file.seek(0)
    filename = file.filename.lower()
    try:
        if filename.endswith((".xlsx", ".xls")):
            raw = pd.read_excel(io.BytesIO(file_content), header=None, engine="openpyxl")
        else:
            raw = pd.read_csv(io.BytesIO(file_content), header=None)
    except Exception:
        return None, None

    def _try_parse_cell(val) -> Optional[tuple[int, int]]:
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return None
        if isinstance(val, (datetime, pd.Timestamp)):
            return val.month, val.year
        s = str(val).strip()
        if not s:
            return None
        try:
            parsed = pd.to_datetime(s, dayfirst=True, errors="coerce")
            if not pd.isna(parsed):
                return int(parsed.month), int(parsed.year)
        except Exception:
            pass

        patterns = [
            r"thang\D*(\d{1,2})\D*nam\D*(20\d{2})",
            r"(\d{1,2})\s*[/-]\s*(20\d{2})",
            r"(\d{1,2})\s+(20\d{2})",
            r"(20\d{2})[-/](\d{1,2})",
        ]
        for pattern in patterns:
            m = re.search(pattern, s, re.IGNORECASE)
            if m:
                try:
                    g1, g2 = m.group(1), m.group(2)
                    m1, m2 = int(g1), int(g2)
                    if m1 > 1900 and 1 <= m2 <= 12:
                        return m2, m1
                    if 1 <= m1 <= 12 and m2 > 1900:
                        return m1, m2
                except Exception:
                    continue

        nums = re.findall(r"\d{1,4}", s)
        if len(nums) >= 2:
            try:
                m_val = int(nums[0])
                y_val = int(nums[1])
                if 1 <= m_val <= 12 and y_val > 1900:
                    return m_val, y_val
                m_val = int(nums[-2])
                y_val = int(nums[-1])
                if 1 <= m_val <= 12 and y_val > 1900:
                    return m_val, y_val
            except Exception:
                pass
        return None

    # DEBUG: print upload snapshot before extraction
    try:
        try:
            print("UPLOAD DEBUG: first 5 rows:")
            preview = raw.head(5)
            try:
                print(preview.values.tolist())
            except Exception:
                print(preview.to_dict(orient="list"))
        except Exception:
            print("UPLOAD DEBUG: unable to print first 5 rows")

        # Print value at row 3, column K (index 10) for debugging
        if raw.shape[0] > 2 and raw.shape[1] > 10:
            try:
                val_row3_k = raw.iat[2, 10]
                print("UPLOAD DEBUG: row 3, column K value:", val_row3_k)
            except Exception:
                print("UPLOAD DEBUG: could not read row 3 column K")
        else:
            print("UPLOAD DEBUG: file too small to read row 3 column K")
    except Exception:
        # ensure debug printing never raises
        pass

    # 1) Priority extraction: check K6 (row index 5, col index 10)
    try:
        if raw.shape[0] > 5 and raw.shape[1] > 10:
            primary = raw.iat[5, 10]
            parsed = _try_parse_cell(primary)
            if parsed:
                print("Đã thiết lập lấy Tháng/Năm ưu tiên tại K6 thành công.")
                return parsed
    except Exception:
        pass

    # 2) Header-based extraction: locate a column header containing "Tháng" or "Month"
    def _find_month_year_from_header() -> Optional[tuple[int, int]]:
        max_rows = min(10, raw.shape[0])
        max_cols = min(20, raw.shape[1])
        keyword_re = re.compile(r"\b(thang|tháng|month)\b", re.IGNORECASE)

        for r in range(max_rows):
            for c in range(max_cols):
                try:
                    cell = raw.iat[r, c]
                except Exception:
                    continue
                if cell is None or (isinstance(cell, float) and pd.isna(cell)):
                    continue
                if isinstance(cell, str) and keyword_re.search(cell):
                    parsed = _try_parse_cell(cell)
                    if parsed:
                        print("Đã thiết lập lấy Tháng/Năm trực tiếp từ ô tiêu đề chứa Tháng/Month.")
                        return parsed

                    # try other values in the same row as a column header
                    for cc in range(max_cols):
                        if cc == c:
                            continue
                        try:
                            candidate = raw.iat[r, cc]
                        except Exception:
                            continue
                        parsed = _try_parse_cell(candidate)
                        if parsed:
                            print(
                                "Đã thiết lập lấy Tháng/Năm từ hàng tiêu đề: đọc giá trị cùng hàng với tiêu đề Tháng/Month."
                            )
                            return parsed

                    # try values in the same column below/above the header
                    for rr in range(max_rows):
                        if rr == r:
                            continue
                        try:
                            candidate = raw.iat[rr, c]
                        except Exception:
                            continue
                        parsed = _try_parse_cell(candidate)
                        if parsed:
                            print(
                                "Đã thiết lập lấy Tháng/Năm từ cột tiêu đề: đọc giá trị trong cùng cột với tiêu đề Tháng/Month."
                            )
                            return parsed
        return None

    parsed = _find_month_year_from_header()
    if parsed:
        return parsed

    # 3) Flexible search fallback: scan a larger region (first 10 rows x 20 columns)
    # This ensures we find Month/Year if it's at K6 or nearby.
    max_rows = min(10, raw.shape[0])
    max_cols = min(20, raw.shape[1])
    keyword_re = re.compile(r"\b(thang|tháng|month)\b", re.IGNORECASE)
    for r in range(max_rows):
        for c in range(max_cols):
            try:
                cell = raw.iat[r, c]
            except Exception:
                continue
            if cell is None or (isinstance(cell, float) and pd.isna(cell)):
                continue
            try:
                if isinstance(cell, str) and keyword_re.search(cell):
                    # try same row first
                    for cc in range(max_cols):
                        candidate = raw.iat[r, cc]
                        parsed = _try_parse_cell(candidate)
                        if parsed:
                            print("Đã thiết lập lấy Tháng/Năm từ vùng quét (Flexible Search) thành công.")
                            return parsed
                    # try nearby rows in same column
                    for rr in range(max_rows):
                        candidate = raw.iat[rr, c]
                        parsed = _try_parse_cell(candidate)
                        if parsed:
                            print("Đã thiết lập lấy Tháng/Năm từ vùng quét (Flexible Search) thành công.")
                            return parsed
            except Exception:
                continue

    # If nothing found, log error and return None
    print("Không thể xác định Tháng/Năm, vui lòng kiểm tra lại cấu trúc file")
    # Print headers (row 5) if available to help debugging
    try:
        if raw.shape[0] > 4:
            headers = raw.iloc[4].tolist()
            print("UPLOAD DEBUG: header row (row 5):", headers)
        else:
            print("UPLOAD DEBUG: no header row available to display")
    except Exception:
        print("UPLOAD DEBUG: unable to print header row")
    return None, None


def read_upload_file(upload_file: UploadFile) -> pd.DataFrame:
    content = upload_file.file.read()
    upload_file.file.seek(0)
    filename = upload_file.filename.lower()
    if filename.endswith(".csv"):
        return pd.read_csv(io.BytesIO(content))
    if filename.endswith(('.xlsx', '.xls')):
        data = pd.read_excel(io.BytesIO(content), engine='openpyxl', header=None)
        if data.shape[0] >= 5:
            header_row = data.iloc[4].tolist()
            data.columns = header_row
            return data.iloc[5:].reset_index(drop=True)
        return data
    raise HTTPException(status_code=400, detail="Unsupported file type. Use CSV or Excel.")

def _clean_social_date(value: Optional[object]) -> Optional[object]:
    """Keep valid social dates intact and only remove empty/invalid placeholders."""
    if value is None or pd.isna(value):
        return None

    if isinstance(value, (datetime, date)):
        return value

    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()

    text = str(value).strip()
    if not text or text.lower() in {'nan', 'nat', 'none', '', 'n/a', 'na', '<na>'}:
        return None

    try:
        parsed = pd.to_datetime(text, dayfirst=True, errors='coerce')
        if pd.isna(parsed):
            return text
        return parsed.to_pydatetime()
    except Exception:
        return text


def normalize_status(value: Optional[str]) -> str:
    if value is None:
        return "Active"
    normalized = str(value).strip()
    if not normalized:
        return "Active"
    lower_value = normalized.lower()
    for keyword, mapped in STATUS_MAP.items():
        if keyword in lower_value:
            return mapped
    return normalized


def parse_month_year(column: pd.Series, df: pd.DataFrame) -> pd.DataFrame:
    if "record_month" in df.columns and "record_year" in df.columns:
        return df

    if column is None:
        return df

    values = []
    for value in column.astype(str).tolist():
        if pd.isna(value) or str(value).strip() == "nan":
            values.append(None)
            continue
        try:
            parsed = pd.to_datetime(str(value).replace("-", "/"), errors="coerce", dayfirst=False)
            values.append(parsed)
        except Exception:
            values.append(None)

    parsed_series = pd.Series(values)
    df["record_month"] = pd.Series(parsed_series.dt.month, dtype="Int64")
    df["record_year"] = pd.Series(parsed_series.dt.year, dtype="Int64")
    return df


def clean_update_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    df = normalize_columns(df)
    if "emp_id" not in df.columns:
        raise HTTPException(status_code=400, detail="Missing Mã NV column.")

    df = df.copy()
    df["emp_id"] = df["emp_id"].astype(str).str.strip()
    df["full_name"] = df.get("full_name", pd.Series([None] * len(df), dtype=object)).astype(str).str.strip().replace({"nan": None})
    df["join_date"] = parse_date_column(df.get("join_date"))
    df["birth_date"] = parse_date_column(df.get("birth_date"))
    df["social_no"] = df.get("social_no", pd.Series([None] * len(df), dtype=object)).astype(str).str.strip().replace({"nan": None})
    df["social_date"] = parse_date_column(df.get("social_date"))
    df["resign_date"] = parse_date_column(df.get("resign_date"))
    df = parse_month_year(df.get("month_year_change"), df)
    try:
        df["record_month"] = pd.to_numeric(df.get("record_month"), errors="coerce").astype("Int64")
        df["record_year"] = pd.to_numeric(df.get("record_year"), errors="coerce").astype("Int64")
    except Exception:
        # Fallback for pandas versions without nullable Int64 dtype
        tmp_month = pd.to_numeric(df.get("record_month"), errors="coerce")
        tmp_year = pd.to_numeric(df.get("record_year"), errors="coerce")
        tmp_month = pd.Series(tmp_month, index=df.index).fillna(0).astype(int)
        tmp_year = pd.Series(tmp_year, index=df.index).fillna(0).astype(int)
        df["record_month"] = tmp_month
        df["record_year"] = tmp_year
    df = df.dropna(subset=["emp_id", "record_month", "record_year"])
    df = df[df["record_month"].between(1, 12)]

    status_values = []
    salary_values = []
    mapping = {"TS": "TS", "OM": "OM", "KL": "KL", "ST": "ST", "NV": "NV", "RESIGNATION": "NV"}
    for _, row in df.iterrows():
        status_value = row.get("status")
        salary_value = row.get("base_salary")
        normalized_status = None
        if status_value is not None and not pd.isna(status_value):
            normalized_status = str(status_value).strip().upper()

        if normalized_status in mapping:
            status_values.append(mapping[normalized_status])
            salary_values.append(0.0)
            continue

        parsed_salary = None
        if salary_value is not None and not pd.isna(salary_value):
            text_value = str(salary_value).strip()
            if text_value:
                cleaned = text_value.replace(",", "").replace(" ", "")
                if re.fullmatch(r"-?\d+(\.\d+)?", cleaned):
                    numeric_value = float(cleaned)
                    parsed_salary = int(numeric_value) if numeric_value.is_integer() else numeric_value

        if normalized_status is not None and normalized_status in {"ACTIVE", ""}:
            if parsed_salary is not None:
                status_values.append("Active")
                salary_values.append(parsed_salary)
            else:
                status_values.append("NV")
                salary_values.append(0.0)
            continue

        if parsed_salary is not None:
            status_values.append("Active")
            salary_values.append(parsed_salary)
        else:
            status_values.append("NV")
            salary_values.append(0.0)

    df["status_in_month"] = status_values
    df["base_salary"] = salary_values
    df["status_normalized"] = df["status_in_month"].apply(normalize_status)

    for val_column in ["bhxh_val", "bhyt_val", "bhtn_val", "bhbnn_val"]:
        df[val_column] = None

    return df


def last_day_of_month(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def _coerce_int(value: object, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return default
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return default


def clean_data_for_db(record_dict: Dict[str, object]) -> Dict[str, object]:
    cleaned = {}
    for key, value in record_dict.items():
        if isinstance(value, float) and np.isnan(value):
            cleaned[key] = None
        elif isinstance(value, (pd.Timestamp, datetime)):
            cleaned[key] = value.date() if hasattr(value, "date") else value
        elif isinstance(value, np.floating) and np.isnan(value):
            cleaned[key] = None
        else:
            cleaned[key] = value

    if "resign_date" in cleaned and cleaned["resign_date"] is not None:
        if isinstance(cleaned["resign_date"], float) and np.isnan(cleaned["resign_date"]):
            cleaned["resign_date"] = None
    if "social_date" in cleaned and cleaned["social_date"] is not None:
        if isinstance(cleaned["social_date"], float) and np.isnan(cleaned["social_date"]):
            cleaned["social_date"] = None
        elif isinstance(cleaned["social_date"], str):
            text = cleaned["social_date"].strip()
            if not text or text.lower() in {"nan", "none", "null", "n/a", "na"}:
                cleaned["social_date"] = None
        elif isinstance(cleaned["social_date"], (datetime, date)):
            if cleaned["social_date"] == datetime(1970, 1, 1):
                cleaned["social_date"] = None
    return cleaned


def _sanitize_history_record(record: PayrollHistory) -> PayrollHistory:
    payload = {}
    for key, value in record.__dict__.items():
        if key == "_sa_instance_state":
            continue
        payload[key] = value

    payload = clean_data_for_db(payload)

    for key in ["record_month", "record_year"]:
        payload[key] = _coerce_int(payload.get(key), 0)

    if payload.get("resign_date") is not None and (isinstance(payload["resign_date"], float) and np.isnan(payload["resign_date"])):
        payload["resign_date"] = None
    if payload.get("resign_date") is None:
        payload["resign_date"] = None

    return PayrollHistory(**payload)


def _delete_monthly_history(session: Session, *, month: int, year: int) -> int:
    deleted_count = (
        session.query(PayrollHistory)
        .filter(PayrollHistory.record_month == month)
        .filter(PayrollHistory.record_year == year)
        .delete(synchronize_session=False)
    )
    return deleted_count


def _replace_monthly_history(session: Session, *, month: int, year: int) -> int:
    return _delete_monthly_history(session, month=month, year=year)


def _should_overwrite_month(*, overwrite: object, existing_count: int) -> bool:
    """Decide whether to wipe-and-reload the target month.

    Deliberately takes ONLY the explicit `overwrite` flag and the current record
    count -- never month/year -- so a specific month can never be hardcoded into
    an always-overwrite bypass again (see project rule: XÓA THÁNG CŨ chỉ được
    thực hiện khi có yêu cầu overwrite rõ ràng, không hardcode theo tháng/năm).
    """
    return str(overwrite).lower() == "true" or existing_count > 0


def _coerce_numeric_salary(value: object) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        numeric_value = float(value)
        return numeric_value if not np.isnan(numeric_value) and numeric_value > 0 else None
    if isinstance(value, str):
        text_value = value.strip()
        if not text_value:
            return None
        cleaned = text_value.replace(",", "").replace(" ", "")
        if re.fullmatch(r"-?\d+(?:\.\d+)?", cleaned):
            numeric_value = float(cleaned)
            return numeric_value if numeric_value > 0 else None
    return None


def _find_last_month_with_salary(
    session: Session,
    *,
    emp_id: str,
    target_month: int,
    target_year: int,
    lookback_months: int = 10,
) -> Optional[PayrollHistory]:
    month_cursor = target_month - 1 if target_month > 1 else 12
    year_cursor = target_year if target_month > 1 else target_year - 1

    for _ in range(lookback_months):
        candidate = (
            session.query(PayrollHistory)
            .filter(PayrollHistory.emp_id == emp_id)
            .filter(PayrollHistory.record_month == month_cursor)
            .filter(PayrollHistory.record_year == year_cursor)
            .order_by(PayrollHistory.record_year, PayrollHistory.record_month)
            .first()
        )
        if candidate is not None and _coerce_numeric_salary(candidate.base_salary) is not None:
            return candidate

        month_cursor = month_cursor - 1 if month_cursor > 1 else 12
        year_cursor = year_cursor if month_cursor != 12 else (year_cursor - 1 if month_cursor == 12 and target_month == 1 else year_cursor)
        if month_cursor == 12:
            year_cursor = year_cursor - 1 if year_cursor > 1 else year_cursor

    return None


def _apply_carry_forward_logic(
    session: Session,
    *,
    target_month: int,
    target_year: int,
    uploaded_emp_ids: set[str],
    manual_review_cases: Optional[List[Dict[str, object]]] = None,
) -> List[PayrollHistory]:
    if not uploaded_emp_ids:
        uploaded_emp_ids = set()

    previous_month = target_month - 1 if target_month > 1 else 12
    previous_year = target_year if target_month > 1 else target_year - 1

    prior_rows = (
        session.query(PayrollHistory)
        .filter(PayrollHistory.record_month == previous_month)
        .filter(PayrollHistory.record_year == previous_year)
        .all()
    )

    existing_target_rows = (
        session.query(PayrollHistory)
        .filter(PayrollHistory.record_month == target_month)
        .filter(PayrollHistory.record_year == target_year)
        .all()
    )
    existing_target_emp_ids = {row.emp_id for row in existing_target_rows}

    carry_forward_records: List[PayrollHistory] = []
    seen_emp_ids = set(existing_target_emp_ids)
    manual_review_cases = manual_review_cases if manual_review_cases is not None else []

    for row in prior_rows:
        if row.emp_id in uploaded_emp_ids or row.emp_id in seen_emp_ids:
            continue

        if row.status_in_month in {"Active", "TS", "OM", "KL", "ST", "NV"}:
            if row.status_in_month in {"TS", "OM", "KL", "ST"}:
                fallback_row = _find_last_month_with_salary(
                    session,
                    emp_id=row.emp_id,
                    target_month=target_month,
                    target_year=target_year,
                )
                if fallback_row is not None:
                    carry_forward_status = fallback_row.status_in_month if fallback_row.status_in_month != "Active" else "Active"
                    carry_forward_salary = fallback_row.base_salary
                    carry_forward_records.append(
                        PayrollHistory(
                            emp_id=row.emp_id,
                            record_month=target_month,
                            record_year=target_year,
                            base_salary=carry_forward_salary,
                            status_in_month=carry_forward_status,
                            resign_date=None,
                            bhxh_val=str(carry_forward_salary) if carry_forward_salary is not None else None,
                            bhyt_val=str(carry_forward_salary) if carry_forward_salary is not None else None,
                            bhtn_val=str(carry_forward_salary) if carry_forward_salary is not None else None,
                            bhbnn_val=str(carry_forward_salary) if carry_forward_salary is not None else None,
                        )
                    )
                else:
                    manual_review_cases.append(
                        {
                            "emp_id": row.emp_id,
                            "target_month": target_month,
                            "target_year": target_year,
                            "reason": "No numeric salary found in prior 10 months for leave-status record",
                        }
                    )
            else:
                carry_forward_status = row.status_in_month if row.status_in_month != "Active" else "Active"
                carry_forward_records.append(
                    PayrollHistory(
                        emp_id=row.emp_id,
                        record_month=target_month,
                        record_year=target_year,
                        base_salary=row.base_salary,
                        status_in_month=carry_forward_status,
                        resign_date=None if carry_forward_status != "NV" else last_day_of_month(target_year, target_month),
                        bhxh_val=str(row.base_salary) if row.base_salary is not None else None,
                        bhyt_val=str(row.base_salary) if row.base_salary is not None else None,
                        bhtn_val=str(row.base_salary) if row.base_salary is not None else None,
                        bhbnn_val=str(row.base_salary) if row.base_salary is not None else None,
                    )
                )
        seen_emp_ids.add(row.emp_id)

    return carry_forward_records


def validate_report_filters(month: int, year: int) -> tuple[int, int]:
    with Session(engine) as session:
        report3_rows = (
            session.query(PayrollHistory)
            .filter(PayrollHistory.record_month == month)
            .filter(PayrollHistory.record_year == year)
            .filter(PayrollHistory.status_in_month == "Active")
            .all()
        )
        report4_rows = (
            session.query(PayrollHistory)
            .filter(PayrollHistory.record_month == month)
            .filter(PayrollHistory.record_year == year)
            .filter(PayrollHistory.status_in_month.in_(["TS", "OM", "KL", "ST", "NV", "RESIGNATION"]))
            .all()
        )

    bad_report3 = [row.status_in_month for row in report3_rows if row.status_in_month in {"TS", "OM", "KL", "ST"}]
    if not report4_rows or bad_report3:
        print(
            f"REPORT_FILTER_CHECK FAILED month={month}/{year}: report3_count={len(report3_rows)} report4_count={len(report4_rows)} bad_report3={bad_report3}"
        )
    else:
        print(
            f"REPORT_FILTER_CHECK OK month={month}/{year}: report3_count={len(report3_rows)} report4_count={len(report4_rows)}"
        )
    return len(report3_rows), len(report4_rows)


@app.on_event("startup")
def startup_event() -> None:
    init_db()


@app.post("/upload-monthly-update")
async def upload_monthly_update(
    file: UploadFile = File(...),
    month: int = Form(...),
    year: int = Form(...),
    overwrite: Optional[str] = Form("false"),
) -> Dict[str, object]:
    file_month, file_year = _extract_month_year_from_upload(file)
    if file_month is None or file_year is None:
        raise HTTPException(
            status_code=400,
            detail=(
                "Không tìm thấy thông tin Tháng/Năm (ô K6, tiêu đề cột Tháng/Month hoặc vùng quét). "
                "Vui lòng đảm bảo file có ô chứa 'Tháng'/'Month' và giá trị tháng/năm gần đó, "
                "hoặc ô K6 chứa Month/Year (ví dụ Excel date hoặc '06-2026'). Xem log server để biết preview file."
            ),
        )
    if file_month != month or file_year != year:
        raise HTTPException(
            status_code=400,
            detail=f"Tháng/năm trong file là {file_month:02d}/{file_year}, không khớp với yêu cầu {month:02d}/{year}.",
        )

    with Session(engine) as session:
        existing_count = session.query(PayrollHistory).filter(
            PayrollHistory.record_month == month,
            PayrollHistory.record_year == year,
        ).count()

    df = read_upload_file(file)
    df = clean_update_dataframe(df)
    status_counts = df["status_in_month"].fillna("Active").value_counts().to_dict()
    for code in ["TS", "OM", "KL", "ST", "NV"]:
        print(f"UPLOAD STATUS COUNTS {code}={status_counts.get(code, 0)}")

    history_records: List[PayrollHistory] = []
    carry_forward_records: List[PayrollHistory] = []

    with Session(engine) as session:
        try:
            should_overwrite = _should_overwrite_month(overwrite=overwrite, existing_count=existing_count)
            if should_overwrite:
                # Snapshot the whole DB before wiping this month's rows. App has
                # no ongoing maintenance after handoff, so this must happen
                # automatically -- it deliberately does NOT delete old backups
                # (see backup_database_file docstring in database.py).
                backup_path = backup_database_file(DATABASE_PATH, BACKUP_DIR)
                if backup_path is not None:
                    print(f"Đã backup app.db trước khi ghi đè tháng {month:02d}/{year}: {backup_path}")
                deleted_count = _delete_monthly_history(session, month=month, year=year)
                current_count = (
                    session.query(PayrollHistory)
                    .filter(PayrollHistory.record_month == month)
                    .filter(PayrollHistory.record_year == year)
                    .count()
                )
                print(
                    f"Đã kích hoạt cơ chế Overwrite: Xóa dữ liệu cũ tháng {month:02d}/{year} trước khi nạp file mới. Tổng số bản ghi tháng {month:02d}/{year} hiện tại: {current_count}."
                )

            uploaded_emp_ids = {str(row.emp_id) for row in df.itertuples(index=False)}
            with session.no_autoflush:
                employee_map = {
                    employee.emp_id: employee
                    for employee in session.query(Employee).filter(Employee.emp_id.in_(df["emp_id"].unique().tolist())).all()
                }

            for row in df.itertuples(index=False):
                employee = employee_map.get(row.emp_id)
                status = row.status_normalized
                salary_value = float(row.base_salary or 0.0)
                is_leave_code = status in {"TS", "OM", "KL", "ST"}

                if not employee:
                    employee_payload = {
                        "emp_id": row.emp_id,
                        "full_name": row.full_name or "Unknown",
                        "join_date": row.join_date,
                        "birth_date": row.birth_date,
                        "social_no": row.social_no,
                        "social_date": row.social_date,
                        "current_status": status,
                        "current_salary": salary_value,
                        "resign_date": row.resign_date if status == "Resigned" else None,
                    }
                    employee = Employee(**clean_data_for_db(employee_payload))
                    session.add(employee)
                    employee_map[row.emp_id] = employee
                else:
                    if row.full_name and row.full_name != employee.full_name:
                        employee.full_name = row.full_name
                    if row.join_date and row.join_date != employee.join_date:
                        employee.join_date = row.join_date
                    if row.birth_date and row.birth_date != employee.birth_date:
                        employee.birth_date = row.birth_date
                    if row.social_no and row.social_no != employee.social_no:
                        employee.social_no = row.social_no
                    if row.social_date and row.social_date != employee.social_date:
                        employee.social_date = row.social_date

                    if status in {"TS", "OM", "KL", "ST"}:
                        employee.current_status = status
                        employee.current_salary = salary_value
                        employee.resign_date = None
                    elif status == "NV":
                        employee.current_status = "NV"
                        employee.resign_date = row.resign_date
                    else:
                        employee.current_status = "Active"
                        employee.current_salary = salary_value

                if status in {"TS", "OM", "KL", "ST"}:
                    employee.resign_date = None
                elif status == "NV" and not employee.resign_date:
                    employee.resign_date = last_day_of_month(int(row.record_year), int(row.record_month))

                insurance_value = status if is_leave_code else str(salary_value)
                history_payload = {
                    "emp_id": row.emp_id,
                    "record_month": int(row.record_month),
                    "record_year": int(row.record_year),
                    "base_salary": salary_value,
                    "status_in_month": row.status_in_month,
                    "resign_date": row.resign_date if status == "NV" else None,
                    "bhxh_val": insurance_value,
                    "bhyt_val": insurance_value,
                    "bhtn_val": insurance_value,
                    "bhbnn_val": insurance_value,
                }
                history_records.append(PayrollHistory(**clean_data_for_db(history_payload)))

            if history_records:
                cleaned_history_records = [_sanitize_history_record(record) for record in history_records]
                session.bulk_save_objects(cleaned_history_records)

            for employee in employee_map.values():
                cleaned_employee = clean_data_for_db(employee.__dict__)
                employee.emp_id = cleaned_employee.get("emp_id", employee.emp_id)
                employee.full_name = cleaned_employee.get("full_name", employee.full_name)
                employee.join_date = cleaned_employee.get("join_date", employee.join_date)
                employee.birth_date = cleaned_employee.get("birth_date", employee.birth_date)
                employee.social_no = cleaned_employee.get("social_no", employee.social_no)
                employee.social_date = cleaned_employee.get("social_date", employee.social_date)
                employee.current_status = cleaned_employee.get("current_status", employee.current_status)
                employee.current_salary = cleaned_employee.get("current_salary", employee.current_salary)
                employee.resign_date = cleaned_employee.get("resign_date", employee.resign_date)

            carry_forward_records = _apply_carry_forward_logic(
                session,
                target_month=month,
                target_year=year,
                uploaded_emp_ids=uploaded_emp_ids,
            )
            if carry_forward_records:
                cleaned_carry_forward_records = [_sanitize_history_record(record) for record in carry_forward_records]
                session.bulk_save_objects(cleaned_carry_forward_records)
                print(
                    f"Đã hoàn tất logic Carry-Forward. Đã sao chép dữ liệu cho {len(carry_forward_records)} nhân viên cũ sang tháng mới."
                )

            session.commit()
            if should_overwrite:
                print(
                    f"Đã xóa dữ liệu cũ tháng {month:02d}/{year} và nạp dữ liệu mới + kế thừa thành công nhân viên cũ từ tháng trước."
                )
        except Exception:
            session.rollback()
            raise

    return {
        "message": "Monthly update processed",
        "records_imported": len(history_records) + len(carry_forward_records),
        "employees_updated": len(employee_map),
        "carry_forward_count": len(carry_forward_records),
    }


@app.get("/upload-monthly-status")
def upload_monthly_status(month: int, year: int) -> Dict[str, object]:
    with Session(engine) as session:
        count = session.query(PayrollHistory).filter(
            PayrollHistory.record_month == month,
            PayrollHistory.record_year == year,
        ).count()
    return {"exists": count > 0, "record_count": count}


def _get_header_parts(column_name: str) -> tuple[str, str]:
    mapping = {
        "STT": ("STT", "No"),
        "STT No": ("STT", "No"),
        "No": ("STT", "No"),
        "Emp ID": ("Mã NV", "Emp ID"),
        "Mã NV": ("Mã NV", "Emp ID"),
        "Full Name": ("Họ và tên", "Full Name"),
        "Họ và tên": ("Họ và tên", "Full Name"),
        "Join Date": ("Ngày vào", "Join Date"),
        "Ngày vào": ("Ngày vào", "Join Date"),
        "Birth Date": ("Ngày sinh", "Birth Date"),
        "Ngày sinh": ("Ngày sinh", "Birth Date"),
        "Social No": ("Sổ BHXH", "Socaial No"),
        "Socaial No": ("Sổ BHXH", "Socaial No"),
        "Sổ BHXH": ("Sổ BHXH", "Socaial No"),
        "Social Date": ("Ngày tham gia BHXH", "Social Date"),
        "Current Status": ("Tình trạng", "Status"),
        "Current Salary": ("Mức lương", "Current Salary"),
        "Resign Date": ("Ngày nghỉ", "End Date"),
        "Month": ("Tháng", "Month"),
        "Year": ("Năm", "Year"),
        "Base Salary": ("Lương cơ bản", "Base Salary"),
        "Status": ("Tình trạng", "Status"),
        "BHXH": ("BHXH", "Social ins."),
        "BHYT": ("BHYT", "Health ins."),
        "BHTN": ("BHTN", "Unemployment ins."),
        "BHBNN": ("BHBNN", "Ocupatinal accident and disease ins."),
    }
    return mapping.get(column_name, (column_name, column_name))


def _is_missing_bhtn_value(value: Optional[str]) -> bool:
    if value is None:
        return True
    normalized = str(value).strip()
    if not normalized:
        return True
    lowered = normalized.lower()
    if lowered in {"none", "nan", "null", "n/a", "na", "0"}:
        return True
    return lowered in {"ts", "om", "kl", "st", "resignation", "resigned", "not participating", "không đóng", "khong dong"}


def _calculate_insurance_values(status: Optional[str], base_salary: Optional[float]) -> Dict[str, object]:
    status_value = str(status or "Active").strip().upper()
    if status_value in {"TS", "OM", "KL", "ST"}:
        return {
            "BHXH": status_value,
            "BHYT": status_value,
            "BHTN": status_value,
            "BHBNN": status_value,
        }

    salary_value = float(base_salary or 0.0)
    cap_value = 46000000.0
    if salary_value > cap_value:
        return {
            "BHXH": cap_value,
            "BHYT": cap_value,
            "BHTN": salary_value,
            "BHBNN": cap_value,
        }
    return {
        "BHXH": salary_value,
        "BHYT": salary_value,
        "BHTN": salary_value,
        "BHBNN": salary_value,
    }


def _build_excel_formats(workbook) -> Dict[str, object]:
    return {
        "title_format": workbook.add_format(
            {
                "bold": True,
                "font_name": "Times New Roman",
                "font_size": 16,
                "align": "left",
                "valign": "vcenter",
                "text_wrap": False,
            }
        ),
        "left_align_format": workbook.add_format(
            {
                "font_name": "Times New Roman",
                "font_size": 16,
                "align": "left",
                "valign": "vcenter",
                "text_wrap": False,
            }
        ),
        "header_format": workbook.add_format(
            {
                "bold": True,
                "font_name": "Times New Roman",
                "font_size": 11,
                "bg_color": "#D3D3D3",
                "border": 1,
                "text_wrap": False,
                "valign": "vcenter",
                "align": "center",
            }
        ),
        "data_format": workbook.add_format(
            {
                "font_name": "Times New Roman",
                "font_size": 11,
                "border": 1,
                "text_wrap": False,
                "valign": "vcenter",
            }
        ),
        "date_format": workbook.add_format(
            {
                "font_name": "Times New Roman",
                "font_size": 11,
                "border": 1,
                "text_wrap": False,
                "valign": "vcenter",
                "num_format": "dd/mm/yyyy",
            }
        ),
        "money_format": workbook.add_format(
            {
                "font_name": "Times New Roman",
                "font_size": 11,
                "border": 1,
                "num_format": "#,##0",
            }
        ),
    }


def _write_report_header(
    worksheet,
    workbook,
    report_month: Optional[int],
    report_year: Optional[int],
    title: str,
    title_en: str,
    detail_text: Optional[str] = None,
    *,
    include_month_year: bool = False,
    table_header_row: int = 6,
) -> None:
    formats = _build_excel_formats(workbook)
    left_format = formats["left_align_format"]

    worksheet.write(0, 0, "HANSOLL VINA CO.,LTD", left_format)
    worksheet.write(2, 0, title, left_format)
    worksheet.write(3, 0, title_en, left_format)

    if include_month_year:
        month_text = (
            f"Tháng {report_month}, năm {report_year}"
            if report_month is not None and report_year is not None
            else "Tháng ..., năm ..."
        )
        month_text_en = (
            f"Month {report_month}, Year {report_year}"
            if report_month is not None and report_year is not None
            else "Month ..., Year ..."
        )
        worksheet.write(4, 2, month_text, left_format)
        worksheet.write(5, 2, month_text_en, left_format)
    elif detail_text:
        worksheet.write(4, 0, detail_text, left_format)

    for row_num in range(max(6, table_header_row + 1)):
        worksheet.set_row(row_num, 24)


def _format_report_table(worksheet, df: pd.DataFrame, workbook, header_bg_color: str, *, table_header_row: int = 6, data_start_row: int = 8, report_type: Optional[str] = None) -> None:
    formats = _build_excel_formats(workbook)
    header_format = workbook.add_format(
        {
            "bold": True,
            "font_name": "Times New Roman",
            "font_size": 11,
            "bg_color": header_bg_color,
            "border": 1,
            "text_wrap": True,
            "valign": "vcenter",
            "align": "center",
        }
    )
    header_wrap_format = workbook.add_format(
        {
            "bold": True,
            "font_name": "Times New Roman",
            "font_size": 11,
            "bg_color": header_bg_color,
            "border": 1,
            "text_wrap": True,
            "valign": "vcenter",
            "align": "center",
        }
    )
    data_format = formats["data_format"]
    date_format = formats["date_format"]
    center_data_format = workbook.add_format({
        "font_name": "Times New Roman",
        "font_size": 11,
        "border": 1,
        "align": "center",
        "valign": "vcenter",
    })
    left_name_format = workbook.add_format({
        "font_name": "Times New Roman",
        "font_size": 11,
        "border": 1,
        "align": "left",
        "valign": "vcenter",
    })

    # Determine social date column index if present
    social_date_index = df.columns.get_loc("Social Date") if "Social Date" in df.columns else None

    # Set column widths per-column to avoid overriding specific columns (e.g. column K).
    # Skip column index 10 (Excel column K) so callers can set it explicitly after formatting.
    for col_idx in range(len(df.columns)):
        if col_idx == 10:
            # intentionally skip column K here; callers set K after formatting
            continue
        if col_idx == 2:
            worksheet.set_column(col_idx, col_idx, 20)
        elif social_date_index is not None and col_idx == social_date_index:
            worksheet.set_column(col_idx, col_idx, 15, date_format)
        else:
            worksheet.set_column(col_idx, col_idx, 11)
    # social_date will use the shared date_format from _build_excel_formats
    social_date_format = date_format

    for col_num, column_name in enumerate(df.columns):
        vietnamese, english = _get_header_parts(column_name)
        worksheet.write(table_header_row, col_num, vietnamese, header_format)
        worksheet.write(table_header_row + 1, col_num, english, header_wrap_format)

    money_columns = {"Base Salary", "Current Salary", "BHXH", "BHYT", "BHTN", "BHBNN"}
    money_format = workbook.add_format(
        {
            "font_name": "Times New Roman",
            "font_size": 11,
            "border": 1,
            "num_format": "#,##0",
        }
    )

    for row_num in range(len(df)):
        for col_num, column_name in enumerate(df.columns):
            value = df.iloc[row_num][column_name]
            if pd.isna(value):
                value = ""
                cell_format = center_data_format
            elif column_name in money_columns and isinstance(value, (int, float)):
                cell_format = money_format
            elif column_name == "Social Date":
                # PHASE 27: write actual datetime objects for Excel and apply date_format
                if pd.isna(value) or value is None or (isinstance(value, str) and not str(value).strip()):
                    value = ""
                    cell_format = center_data_format
                elif isinstance(value, pd.Timestamp):
                    value = value.to_pydatetime()
                    cell_format = date_format
                elif isinstance(value, datetime):
                    cell_format = date_format
                elif isinstance(value, date):
                    value = datetime.combine(value, time.min)
                    cell_format = date_format
                else:
                    # Try parsing any remaining string into datetime
                    try:
                        parsed = pd.to_datetime(str(value).strip(), dayfirst=True, errors="coerce")
                        if pd.isna(parsed):
                            value = ""
                            cell_format = center_data_format
                        else:
                            value = parsed.to_pydatetime()
                            cell_format = date_format
                    except Exception:
                        value = ""
                        cell_format = data_format
            elif isinstance(value, datetime):
                cell_format = date_format
            elif isinstance(value, date):
                value = datetime.combine(value, time.min)
                cell_format = date_format
            else:
                cell_format = center_data_format
            # Override for Name column (index 2) to left-align
            if col_num == 2:
                cell_format = left_name_format
            worksheet.write(row_num + data_start_row, col_num, value, cell_format)

    # NOTE: Do not set header or data row heights here to avoid overriding caller-specific
    # layout settings (e.g. callers may set different heights per report). Callers should
    # set `worksheet.set_row(...)` and any report-specific `set_column(...)` (like 'K:K')
    # after calling this function.
    worksheet.freeze_panes(data_start_row, 0)


@app.get("/export-report-2")
def export_report_2(emp_id: str) -> StreamingResponse:
    with Session(engine) as session:
        employee = session.query(Employee).filter(Employee.emp_id == emp_id).first()
        if not employee:
            raise HTTPException(status_code=404, detail="Employee not found")

        history_rows = (
            session.query(PayrollHistory)
            .filter(PayrollHistory.emp_id == emp_id)
            .order_by(PayrollHistory.record_year, PayrollHistory.record_month)
            .all()
        )

    rows = []
    for idx, history in enumerate(history_rows, start=1):
        insurance_values = _calculate_insurance_values(history.status_in_month, history.base_salary)
        rows.append(
            {
                "STT": idx,
                "Emp ID": employee.emp_id,
                "Full Name": employee.full_name,
                "Month": history.record_month,
                "Year": history.record_year,
                "Status": history.status_in_month,
                "Base Salary": history.base_salary,
                "BHXH": insurance_values["BHXH"],
                "BHYT": insurance_values["BHYT"],
                "BHTN": insurance_values["BHTN"],
                "BHBNN": insurance_values["BHBNN"],
            }
        )

    df = pd.DataFrame(rows).drop_duplicates(subset=["Emp ID", "Month", "Year"], keep="last")
    df = df.dropna(subset=["Emp ID"])
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, header=False, sheet_name="Report2", startrow=8)
        workbook = writer.book
        worksheet = writer.sheets["Report2"]
        detail_text = f"Mã NV - Họ tên: {employee.emp_id} - {employee.full_name}"
        report_title = f"LỊCH_SỬ_ĐÓNG_BẢO_HIỂM_{employee.emp_id}_{employee.full_name}"
        _write_report_header(
            worksheet,
            workbook,
            None,
            None,
            "LỊCH SỬ ĐÓNG BẢO HIỂM CÁ NHÂN",
            "PERSONAL INSURANCE HISTORY",
            detail_text,
            include_month_year=False,
            table_header_row=5,
        )
        _format_report_table(worksheet, df, workbook, "#E6F2FF", table_header_row=6, data_start_row=8, report_type='report2')
        # override row heights for Report 2 after formatting
        worksheet.set_row(6, 30)
        worksheet.set_row(7, 50)
        # set column K width for Report 2 (moved after formatting to avoid being overridden)
        worksheet.set_column('K:K', 13)

        bhtn_codes = df["BHTN"].fillna("").astype(str).str.strip().str.upper()
        summary_rows = [
            ("Tổng số tháng TS", int((bhtn_codes == "TS").sum())),
            ("Tổng số tháng OM", int((bhtn_codes == "OM").sum())),
            ("Tổng số tháng KL", int((bhtn_codes == "KL").sum())),
            ("Tổng số tháng ST", int((bhtn_codes == "ST").sum())),
        ]
        footer_row = len(df) + 9
        footer_format = workbook.add_format({"font_size": 16, "bold": True, "align": "left", "text_wrap": False})
        worksheet.write(footer_row, 0, "Báo cáo quá trình không tham gia Bảo hiểm thất nghiệp", footer_format)
        summary_start_row = footer_row + 1
        box_format = workbook.add_format({"bold": True, "font_name": "Times New Roman", "font_size": 11, "bg_color": "#E6F2FF", "border": 1})
        for idx, (label, value) in enumerate(summary_rows):
            worksheet.write(summary_start_row + idx, 0, label, box_format)
            worksheet.write(summary_start_row + idx, 1, "", box_format)
            worksheet.write(summary_start_row + idx, 2, value, box_format)

    output.seek(0)
    # use the custom report_title set earlier for personal report filename
    report_title_final = report_title if "report_title" in locals() else _load_report_template_title("Report 2")
    filename = _normalize_filename_for_export(report_title_final, 0, 0)
    if filename.endswith("_00_00.xlsx"):
        filename = filename.replace("_00_00", f"_{emp_id}")
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.get("/export-report-3")
def export_report_3(month: Optional[int] = None, year: Optional[int] = None) -> StreamingResponse:
    if month is None or year is None:
        raise HTTPException(status_code=400, detail="month and year are required")

    with Session(engine) as session:
        results = (
            session.query(PayrollHistory, Employee)
            .outerjoin(Employee, PayrollHistory.emp_id == Employee.emp_id)
            .filter(PayrollHistory.record_month == month)
            .filter(PayrollHistory.record_year == year)
            .filter(PayrollHistory.status_in_month == "Active")
            .order_by(PayrollHistory.emp_id)
            .all()
        )

    rows = []
    for idx, (history, employee) in enumerate(results, start=1):
        status_value = (history.status_in_month or "Active").strip()
        insurance_values = _calculate_insurance_values(status_value, history.base_salary)

        # Clean social_date to remove 1970 dates and invalid values
        social_date_value = _clean_social_date(employee.social_date) if employee is not None else None

        rows.append(
            {
                "STT": idx,
                "Mã NV": history.emp_id,
                "Họ và tên": employee.full_name if employee is not None else None,
                "Ngày vào": employee.join_date if employee is not None else None,
                "Ngày sinh": employee.birth_date if employee is not None else None,
                "Sổ BHXH": employee.social_no if employee is not None else None,
                "Social Date": social_date_value,
                "BHXH": insurance_values["BHXH"],
                "BHYT": insurance_values["BHYT"],
                "BHTN": insurance_values["BHTN"],
                "BHBNN": insurance_values["BHBNN"],
            }
        )

    df = pd.DataFrame(rows, columns=["STT", "Mã NV", "Họ và tên", "Ngày vào", "Ngày sinh", "Sổ BHXH", "Social Date", "BHXH", "BHYT", "BHTN", "BHBNN"])
    df = df.dropna(subset=["Mã NV"])
    # PHASE 27: Ensure Social Date column contains true datetime values
    if "Social Date" in df.columns:
        def _to_datetime_or_nat(x):
            if pd.isna(x) or x is None or (isinstance(x, str) and not x.strip()):
                return pd.NaT
            if isinstance(x, (datetime, date)):
                return pd.Timestamp(x)
            if isinstance(x, pd.Timestamp):
                return x
            try:
                if isinstance(x, (int, float)) and not isinstance(x, bool):
                    return pd.to_datetime(x, unit="D", origin="1899-12-30", errors="coerce")
                s = str(x).strip()
                if re.fullmatch(r"\d+(?:\.\d+)?", s):
                    num = float(s)
                    return pd.to_datetime(num, unit="D", origin="1899-12-30", errors="coerce")
                return pd.to_datetime(s, dayfirst=True, errors="coerce")
            except Exception:
                return pd.NaT

        df["Social Date"] = df["Social Date"].apply(_to_datetime_or_nat)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, header=False, sheet_name="Report3", startrow=8)
        workbook = writer.book
        worksheet = writer.sheets["Report3"]
        worksheet.set_column(0, 9, 11)
        worksheet.set_column(2, 2, 20)
        _write_report_header(
            worksheet,
            workbook,
            month,
            year,
            "DANH SÁCH NGƯỜI LAO ĐỘNG ĐANG LÀM VIỆC",
            "LIST OF WORKING EMPLOYEES",
            include_month_year=True,
        )
        _format_report_table(worksheet, df, workbook, "#E6F2FF", report_type='report3')
        # override row heights for Report 3 after formatting
        worksheet.set_row(6, 30)
        worksheet.set_row(7, 50)
        # set column K width for Report 3 (moved after formatting to avoid being overridden)
        worksheet.set_column('K:K', 13)

    output.seek(0)
    report_title = _load_report_template_title("Report 3")
    filename = _normalize_filename_for_export(report_title, month or 0, year or 0)
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.get("/export-report-4")
def export_report_4(month: Optional[int] = None, year: Optional[int] = None) -> StreamingResponse:
    if month is None or year is None:
        raise HTTPException(status_code=400, detail="month and year are required")

    with Session(engine) as session:
        results = (
            session.query(PayrollHistory, Employee)
            .outerjoin(Employee, PayrollHistory.emp_id == Employee.emp_id)
            .filter(PayrollHistory.record_month == month)
            .filter(PayrollHistory.record_year == year)
            .filter(PayrollHistory.status_in_month.in_(["TS", "OM", "KL", "ST", "NV", "RESIGNATION"]))
            .order_by(PayrollHistory.emp_id)
            .all()
        )

    rows = []
    for idx, (history, employee) in enumerate(results, start=1):
        current_status = ""
        if employee is not None:
            current_status = str(getattr(employee, "current_status", "") or "").strip().upper()

        raw_status = (history.status_in_month or "").strip().upper()

        if raw_status in {"TS", "OM", "KL", "ST"}:
            status_label = raw_status
        elif current_status in {"TS", "OM", "KL", "ST"}:
            status_label = current_status
        elif raw_status in {"NV", "RESIGNATION", "RESIGNED"}:
            status_label = "Nghỉ việc"
        elif current_status in {"NV", "RESIGNATION", "RESIGNED"}:
            status_label = "Nghỉ việc"
        elif current_status in {"", "ACTIVE"}:
            status_label = ""
        else:
            status_label = raw_status or current_status or ""

        social_date_value = _clean_social_date(employee.social_date) if employee is not None else None
        if isinstance(social_date_value, datetime):
            social_date_value = social_date_value.date()
        elif isinstance(social_date_value, pd.Timestamp):
            social_date_value = social_date_value.to_pydatetime().date()

        rows.append(
            {
                "STT": idx,
                "Emp ID": history.emp_id,
                "Full Name": employee.full_name if employee is not None else None,
                "Join Date": employee.join_date if employee is not None else None,
                "Birth Date": employee.birth_date if employee is not None else None,
                "Social No": employee.social_no if employee is not None else None,
                "Social Date": social_date_value,
                "Current Status": status_label,
            }
        )

    df = pd.DataFrame(rows)
    # PHASE 27: Ensure Social Date column contains true datetime values
    if "Social Date" in df.columns:
        def _to_datetime_or_nat(x):
            if pd.isna(x) or x is None or (isinstance(x, str) and not x.strip()):
                return pd.NaT
            if isinstance(x, (datetime, date)):
                return pd.Timestamp(x)
            if isinstance(x, pd.Timestamp):
                return x
            try:
                if isinstance(x, (int, float)) and not isinstance(x, bool):
                    return pd.to_datetime(x, unit="D", origin="1899-12-30", errors="coerce")
                s = str(x).strip()
                if re.fullmatch(r"\d+(?:\.\d+)?", s):
                    num = float(s)
                    return pd.to_datetime(num, unit="D", origin="1899-12-30", errors="coerce")
                return pd.to_datetime(s, dayfirst=True, errors="coerce")
            except Exception:
                return pd.NaT

        df["Social Date"] = df["Social Date"].apply(_to_datetime_or_nat)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, header=False, sheet_name="Report4", startrow=8)
        workbook = writer.book
        worksheet = writer.sheets["Report4"]
        worksheet.set_row(6, 45)
        worksheet.set_row(7, 75)
        worksheet.set_column(0, 9, 11)
        worksheet.set_column(2, 2, 20)
        _write_report_header(
            worksheet,
            workbook,
            month,
            year,
            "DANH SÁCH NGƯỜI LAO ĐỘNG NGHỈ VIỆC",
            "LIST OF RESIGNED EMPLOYEES",
            include_month_year=True,
            table_header_row=6,
        )
        _format_report_table(worksheet, df, workbook, "#F2DCDB", table_header_row=6, data_start_row=8, report_type='report4')
        worksheet.set_row(6, 30)
        worksheet.set_row(7, 30)
    output.seek(0)
    report_title = _load_report_template_title("Report 4")
    filename = _normalize_filename_for_export(report_title, month, year)
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
