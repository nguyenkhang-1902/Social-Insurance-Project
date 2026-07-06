import io
import re
from datetime import date, datetime

import pandas as pd
import requests
import streamlit as st

BACKEND_URL = "http://localhost:8000"

st.set_page_config(page_title="HR ETL Dashboard", layout="wide")
st.title("HR ETL Dashboard")

current_year = datetime.now().year
col1, col2 = st.columns(2)
with col1:
    month = st.number_input("Chọn Tháng (Month)", min_value=1, max_value=12, value=datetime.now().month, step=1)
with col2:
    year = st.number_input("Chọn Năm (Year)", min_value=2009, max_value=2050, value=current_year, step=1)

st.markdown("---")
st.subheader("1. Cập nhật dữ liệu hàng tháng")

uploaded_file = st.file_uploader("Chọn file dữ liệu tháng (Excel hoặc CSV)", type=["xlsx", "xls", "csv"])

if "pending_upload_bytes" not in st.session_state:
    st.session_state["pending_upload_bytes"] = None
if "file_validated" not in st.session_state:
    st.session_state["file_validated"] = False
if "file_month_year" not in st.session_state:
    st.session_state["file_month_year"] = None


def _parse_month_year_from_row(row):
    if row is None:
        return None, None
    text_candidates = []
    for value in row.tolist():
        if pd.isna(value):
            continue
        if isinstance(value, datetime):
            return value.month, value.year
        text_candidates.append(str(value))

    text = " ".join(text_candidates)
    patterns = [
        r"tháng\D*(\d{1,2})\D*năm\D*(20\d{2})",
        r"(\d{1,2})\s*[/-]\s*(20\d{2})",
        r"(\d{1,2})\s+(\d{4})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return int(match.group(1)), int(match.group(2))

    numbers = re.findall(r"\d{1,4}", text)
    if len(numbers) >= 2:
        month_value = int(numbers[0])
        year_value = int(numbers[1])
        if 1 <= month_value <= 12 and year_value > 1900:
            return month_value, year_value

    return None, None


def _parse_file_month_year(file_bytes, filename):
    if filename.lower().endswith((".xlsx", ".xls")):
        raw = pd.read_excel(io.BytesIO(file_bytes), header=None, engine="openpyxl")
    else:
        raw = pd.read_csv(io.BytesIO(file_bytes), header=None)

    max_rows = min(10, raw.shape[0])
    max_cols = min(20, raw.shape[1])
    keyword_re = re.compile(r"\b(thang|tháng|month)\b", re.IGNORECASE)

    for r in range(max_rows):
        row = raw.iloc[r]
        if any(isinstance(val, str) and keyword_re.search(val) for val in row.tolist() if not pd.isna(val)):
            month_year = _parse_month_year_from_row(row)
            if month_year != (None, None):
                return month_year
            # try first non-empty value in same column below
            for c in range(max_cols):
                cell = raw.iat[r, c]
                if isinstance(cell, str) and keyword_re.search(cell):
                    for rr in range(r + 1, max_rows):
                        try:
                            candidate = raw.iat[rr, c]
                        except Exception:
                            continue
                        if pd.isna(candidate):
                            continue
                        if isinstance(candidate, datetime):
                            return candidate.month, candidate.year
                        parsed_month, parsed_year = _parse_month_year_from_row(raw.iloc[rr])
                        if parsed_month is not None and parsed_year is not None:
                            return parsed_month, parsed_year
    return None, None


def _filename_from_response(response):
    content_disposition = response.headers.get("content-disposition", "")
    match = re.search(r'filename="?([^";]+)"?', content_disposition)
    return match.group(1) if match else None


if uploaded_file is not None:
    try:
        file_bytes = uploaded_file.getvalue()
        file_month, file_year = _parse_file_month_year(file_bytes, uploaded_file.name)

        if file_month is None or file_year is None:
            st.error(
                "Không tìm thấy thông tin tháng/năm trong file. Vui lòng đảm bảo file có ô chứa 'Tháng'/'Month' và giá trị tháng/năm gần đó."
            )
            st.session_state["file_validated"] = False
            st.session_state["pending_upload_bytes"] = None
        elif file_month != month or file_year != year:
            st.error(
                f"Tháng/năm trong file là {file_month:02d}/{file_year}, "
                f"không khớp với lựa chọn của bạn: {month:02d}/{year}. "
                "Vui lòng chọn lại."
            )
            st.session_state["file_validated"] = False
            st.session_state["pending_upload_bytes"] = None
        else:
            st.success(f"File hợp lệ cho tháng {file_month:02d}/{file_year}.")
            st.session_state["pending_upload_bytes"] = file_bytes
            st.session_state["file_validated"] = True
            st.session_state["file_month_year"] = (file_month, file_year)

            try:
                status_response = requests.get(
                    f"{BACKEND_URL}/upload-monthly-status",
                    params={"month": month, "year": year},
                    timeout=30,
                )
                if status_response.ok:
                    status_data = status_response.json()
                    if status_data.get("exists"):
                        st.warning(
                            f"Dữ liệu tháng {month:02d}/{year} đã tồn tại trong hệ thống ({status_data.get('record_count', 0)} bản ghi)."
                        )
                    else:
                        st.info(f"Dữ liệu tháng {month:02d}/{year} chưa tồn tại trong hệ thống.")
                else:
                    st.error(
                        f"Lỗi khi kiểm tra dữ liệu hiện có: {status_response.status_code} - {status_response.text}"
                    )
            except Exception as exc:
                st.error(f"Lỗi khi kiểm tra trạng thái upload: {exc}")

    except Exception as exc:
        st.error(f"Không thể đọc file để kiểm tra metadata: {exc}")
        st.session_state["file_validated"] = False
        st.session_state["pending_upload_bytes"] = None

if st.session_state.get("file_validated"):
    st.caption(f"Bạn có chắc chắn muốn cập nhật/ghi đè dữ liệu tháng {month:02d}/{year} không?")
    if st.button("Xác nhận cập nhật"):
        try:
            response = requests.post(
                f"{BACKEND_URL}/upload-monthly-update",
                data={"month": month, "year": year, "overwrite": "true"},
                files={
                    "file": (
                        uploaded_file.name,
                        st.session_state["pending_upload_bytes"],
                        uploaded_file.type or "application/octet-stream",
                    )
                },
                timeout=120,
            )
            if response.ok:
                st.success(response.json().get("message", "Cập nhật thành công."))
                st.write(response.json())
                st.session_state["file_validated"] = False
                st.session_state["pending_upload_bytes"] = None
            else:
                st.error(f"Lỗi API: {response.status_code} - {response.text}")
        except Exception as exc:
            st.error(f"Lỗi khi gửi file: {exc}")

st.markdown("---")
st.subheader("2. Xuất báo cáo")
st.subheader("Báo cáo cá nhân")
employee_id = st.text_input("Nhập Mã Nhân Viên cần in báo cáo cá nhân")

personal_col1, personal_col2 = st.columns(2)
with personal_col1:
    if st.button("Tải Report Cá nhân"):
        if not employee_id.strip():
            st.warning("Vui lòng nhập mã nhân viên trước khi tải report.")
        else:
            try:
                response = requests.get(
                    f"{BACKEND_URL}/export-report-2",
                    params={"emp_id": employee_id.strip()},
                    timeout=60,
                )
                if response.ok:
                    file_name = _filename_from_response(response) or f"report_2_personal_history_{employee_id.strip()}.xlsx"
                    st.download_button(
                        label="Tải file Excel Report",
                        data=response.content,
                        file_name=file_name,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
                elif response.status_code == 404:
                    st.warning("Mã nhân viên không tồn tại trong hệ thống!")
                else:
                    st.error(f"Lỗi API: {response.status_code} - {response.text}")
            except Exception as exc:
                st.error(f"Lỗi khi truy vấn API: {exc}")

st.subheader("Báo cáo tổng hợp tháng")
col1, col2 = st.columns(2)
with col1:
    if st.button("Tải Danh sách Đang làm việc"):
        try:
            response = requests.get(
                f"{BACKEND_URL}/export-report-3",
                params={"month": month, "year": year},
                timeout=60,
            )
            if response.ok:
                file_name = _filename_from_response(response) or f"report_3_working_employees_{month}_{year}.xlsx"
                st.download_button(
                    label="Tải file Excel Report",
                    data=response.content,
                    file_name=file_name,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            else:
                st.error(f"Lỗi API: {response.status_code} - {response.text}")
        except Exception as exc:
            st.error(f"Lỗi khi truy vấn API: {exc}")

with col2:
    if st.button("Tải Danh sách Nhân viên nghỉ việc)"):
        try:
            response = requests.get(
                f"{BACKEND_URL}/export-report-4",
                params={"month": month, "year": year},
                timeout=60,
            )
            if response.ok:
                file_name = _filename_from_response(response) or f"report_4_resigned_employees_{month}_{year}.xlsx"
                st.download_button(
                    label="Tải file Excel Report",
                    data=response.content,
                    file_name=file_name,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            else:
                st.error(f"Lỗi API: {response.status_code} - {response.text}")
        except Exception as exc:
            st.error(f"Lỗi khi truy vấn API: {exc}")
