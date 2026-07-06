"""System integrity smoke test suite (Phase 44).

Run this AFTER starting the app (CHAY_CHUONG_TRINH.bat) to verify the whole
stack end-to-end before handing the project off. It talks to the already
running backend (127.0.0.1:8000) and dashboard (127.0.0.1:8501) over HTTP,
exactly like a real user would.

Safety: database/Sample.xlsx looks like a throwaway fixture but is NOT one --
alongside a handful of synthetic rows it also carries ~59 rows keyed by real,
pre-existing employee IDs (a real June/2026 monthly update someone saved
there). Uploading it with overwrite semantics against a month that already
has real data deletes that real data first, and a diff-based teardown can
only undo *additions*, not *deletions* -- there is no way to safely reuse
that file here. So this suite builds its own upload fixture in-memory,
entirely for the year 2099, which cannot ever collide with real payroll data
(the real dataset only spans 2009-2026). Both the "previous month" carry
-forward source and the uploaded month live in that sandboxed year, and
teardown deletes everything scoped to record_year == SAFE_TEST_YEAR plus the
specific synthetic emp_ids used -- nothing that predates this run is ever
touched.

Run with a single command:
    python test_system_integrity.py
(or, using the bundled portable interpreter:)
    .\\python-3.13.14-embed-amd64\\python.exe test_system_integrity.py
"""
import io
import logging
import sys
import unittest
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

ROOT_DIR = Path(__file__).resolve().parent
CODE_DIR = ROOT_DIR / "Code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from database import engine  # noqa: E402
from models import Employee, PayrollHistory  # noqa: E402

BACKEND_URL = "http://127.0.0.1:8000"
DASHBOARD_URL = "http://127.0.0.1:8501"

# A year outside the real dataset's 2009-2026 range, so this suite can never
# collide with -- or need to delete -- genuine payroll data.
SAFE_TEST_YEAR = 2099
UPLOAD_MONTH = 6
PREV_MONTH = 5

# Employees carried over from the "previous month" (seeded directly, not via
# upload) to prove carry-forward actually ran.
CARRY_FORWARD_EMP_IDS = ["99101", "99102"]

# Employees delivered through the monthly-update upload itself.
UPLOAD_EMP_STATUS = {"99001": "TS", "99002": "KL", "99003": "OM"}
RESIGNED_EMP_ID = "99004"

ALL_TEST_EMP_IDS = CARRY_FORWARD_EMP_IDS + list(UPLOAD_EMP_STATUS) + [RESIGNED_EMP_ID]

LOG_DIR = ROOT_DIR / "Data" / "test_logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / f"test_system_integrity_{datetime.now():%Y%m%d_%H%M%S}.log"

logger = logging.getLogger("system_integrity")
logger.setLevel(logging.INFO)
_file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
_file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger.addHandler(_file_handler)


class LoggingTestResult(unittest.TextTestResult):
    """Mirrors failures/errors into LOG_FILE so a run can be inspected later without re-running it."""

    def addFailure(self, test, err):
        super().addFailure(test, err)
        logger.error("FAIL: %s\n%s", test, self._exc_info_to_string(err, test))

    def addError(self, test, err):
        super().addError(test, err)
        logger.error("ERROR: %s\n%s", test, self._exc_info_to_string(err, test))

    def addSuccess(self, test):
        super().addSuccess(test)
        logger.info("OK: %s", test)


def _read_report_rows(content: bytes) -> pd.DataFrame:
    """All three report endpoints write real data starting at Excel row 8 (0-indexed)."""
    df = pd.read_excel(io.BytesIO(content), header=None, skiprows=8)
    return df.dropna(how="all")


def _build_upload_file(rows: list[dict], month: int, year: int) -> io.BytesIO:
    """Build an in-memory .xlsx matching the monthly-update layout the backend
    expects (title rows, header at row 4, data from row 5, K6-style month/year
    marker), populated only with the given synthetic rows."""
    headers = [
        "STT\nNo",
        "Mã NV\nEmp ID",
        "Họ và tên\nFull Name",
        "Ngày vào\nJoin Date",
        "Ngày sinh\nBirth Date",
        "Sổ BHXH\nSocaial No",
        "BẮT ĐẦU THAM GIA BHXH TẠI HSV.\nSTART JOINING SOCIAL INS AT HSV.",
        "Giới tính\nSex",
        " Tình trạng                              Status",
        "Mức lương mới            New Salary",
        "Tháng - Năm                     Month - Year",
    ]
    data = [[None] * len(headers) for _ in range(4 + 1 + len(rows))]
    data[1][0] = f"DANH SÁCH THAY ĐỔI NGƯỜI LAO ĐỘNG THÁNG {month:02d}-{year} (TEST DATA)"
    data[4] = headers
    for i, row in enumerate(rows):
        r = 5 + i
        data[r][0] = i + 1
        data[r][1] = row["emp_id"]
        data[r][2] = row["full_name"]
        data[r][3] = datetime(2020, 1, 1)
        data[r][4] = datetime(1990, 1, 1)
        data[r][5] = f"TEST{row['emp_id']}"
        data[r][6] = datetime(2020, 1, 1)
        data[r][7] = "Nữ"
        data[r][8] = row["status"]
        data[r][9] = row["status"]
        data[r][10] = datetime(year, month, 1)

    df = pd.DataFrame(data)
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, header=False)
    buffer.seek(0)
    return buffer


class TestSystemIntegrity(unittest.TestCase):
    """Test methods are named test_1_.. test_5_.. so unittest's default alphabetical
    ordering runs them in the required sequence: TC2 (upload) must complete before
    TC3/4/5 can check its effects."""

    _upload_response = None

    @classmethod
    def setUpClass(cls):
        try:
            requests.get(f"{BACKEND_URL}/docs", timeout=5)
        except requests.exceptions.RequestException as exc:
            raise unittest.SkipTest(
                f"Khong ket noi duoc backend tai {BACKEND_URL}. "
                f"Hay chay CHAY_CHUONG_TRINH.bat truoc khi chay bo test nay. Chi tiet: {exc}"
            )

        status_resp = requests.get(
            f"{BACKEND_URL}/upload-monthly-status",
            params={"month": UPLOAD_MONTH, "year": SAFE_TEST_YEAR},
            timeout=10,
        )
        if status_resp.ok and status_resp.json().get("exists"):
            raise unittest.SkipTest(
                f"Da co du lieu o thang {UPLOAD_MONTH}/{SAFE_TEST_YEAR} (khong con 'an toan' de test). "
                "Hay don du lieu test cu (xem test_system_integrity.py) roi chay lai."
            )

        # Seed a synthetic "previous month" with Active employees directly (not
        # through the API) so carry-forward has something deterministic to act on.
        with Session(engine) as session:
            for emp_id in CARRY_FORWARD_EMP_IDS:
                session.add(
                    Employee(
                        emp_id=emp_id,
                        full_name=f"TEST CARRY {emp_id}",
                        current_status="Active",
                        current_salary=10000000.0,
                    )
                )
                session.add(
                    PayrollHistory(
                        emp_id=emp_id,
                        record_month=PREV_MONTH,
                        record_year=SAFE_TEST_YEAR,
                        base_salary=10000000.0,
                        status_in_month="Active",
                    )
                )
            session.commit()
        logger.info("Da seed %d nhan vien Active o thang %s/%s de test carry-forward.",
                    len(CARRY_FORWARD_EMP_IDS), PREV_MONTH, SAFE_TEST_YEAR)

    @classmethod
    def tearDownClass(cls):
        """Everything this suite touches lives under record_year == SAFE_TEST_YEAR
        or one of the explicit synthetic emp_ids -- safe to unconditionally wipe."""
        with Session(engine) as session:
            deleted_history = session.execute(
                text("DELETE FROM payroll_history WHERE record_year = :y"), {"y": SAFE_TEST_YEAR}
            ).rowcount
            deleted_employees = session.execute(
                text("DELETE FROM employee WHERE emp_id IN :ids").bindparams(bindparam("ids", expanding=True)),
                {"ids": ALL_TEST_EMP_IDS},
            ).rowcount
            session.commit()
        logger.info(
            "Don dep xong: xoa %d ban ghi payroll_history (nam %s) va %d nhan vien test.",
            deleted_history, SAFE_TEST_YEAR, deleted_employees,
        )

    # ------------------------------------------------------------------
    # TEST CASE 1: server connectivity
    # ------------------------------------------------------------------
    def test_1_server_ports_respond(self):
        try:
            backend_resp = requests.get(f"{BACKEND_URL}/docs", timeout=10)
        except requests.exceptions.RequestException as exc:
            self.fail(f"Backend (cong 8000) khong phan hoi: {exc}")
        self.assertEqual(backend_resp.status_code, 200, "Backend (cong 8000) khong tra ve 200.")

        try:
            dashboard_resp = requests.get(DASHBOARD_URL, timeout=10)
        except requests.exceptions.RequestException as exc:
            self.fail(f"Dashboard (cong 8501) khong phan hoi: {exc}")
        self.assertEqual(dashboard_resp.status_code, 200, "Dashboard (cong 8501) khong tra ve 200.")

    # ------------------------------------------------------------------
    # TEST CASE 2: upload a valid monthly Excel file
    # ------------------------------------------------------------------
    def test_2_upload_monthly_file(self):
        rows = [
            {"emp_id": emp_id, "full_name": f"TEST UPLOAD {emp_id}", "status": status}
            for emp_id, status in UPLOAD_EMP_STATUS.items()
        ] + [{"emp_id": RESIGNED_EMP_ID, "full_name": f"TEST UPLOAD {RESIGNED_EMP_ID}", "status": "NV"}]
        upload_bytes = _build_upload_file(rows, UPLOAD_MONTH, SAFE_TEST_YEAR)

        response = requests.post(
            f"{BACKEND_URL}/upload-monthly-update",
            data={"month": UPLOAD_MONTH, "year": SAFE_TEST_YEAR, "overwrite": "false"},
            files={
                "file": (
                    "test_upload.xlsx",
                    upload_bytes,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
            timeout=60,
        )
        self.assertEqual(response.status_code, 200, f"Upload that bai: {response.status_code} - {response.text}")
        payload = response.json()
        self.assertIn("Monthly update processed", payload.get("message", ""))
        type(self)._upload_response = payload

    # ------------------------------------------------------------------
    # TEST CASE 3: personal history (Report 2)
    # ------------------------------------------------------------------
    def test_3_personal_report_includes_new_month(self):
        # Sanity check: a real, long-tenured employee's Report 2 still works
        # (read-only, unrelated to this run's synthetic data).
        history_resp = requests.get(f"{BACKEND_URL}/export-report-2", params={"emp_id": "16048"}, timeout=30)
        self.assertEqual(history_resp.status_code, 200)
        history_df = _read_report_rows(history_resp.content)
        self.assertGreater(len(history_df), 0, "Report 2 cho NV 16048 khong co du lieu lich su.")

        # The freshly uploaded employee must show up with the just-uploaded month.
        emp_id = next(iter(UPLOAD_EMP_STATUS))
        resp = requests.get(f"{BACKEND_URL}/export-report-2", params={"emp_id": emp_id}, timeout=30)
        self.assertEqual(resp.status_code, 200)
        df = _read_report_rows(resp.content)
        # Columns: STT, Emp ID, Full Name, Month, Year, Status, Base Salary, BHXH, BHYT, BHTN, BHBNN
        matched = df[(df[3] == UPLOAD_MONTH) & (df[4] == SAFE_TEST_YEAR)]
        self.assertEqual(len(matched), 1, f"Khong thay thang {UPLOAD_MONTH}/{SAFE_TEST_YEAR} trong lich su NV {emp_id}.")
        row = matched.iloc[0]
        self.assertEqual(str(row[5]).strip().upper(), UPLOAD_EMP_STATUS[emp_id])
        for col in (7, 8, 9, 10):
            self.assertTrue(
                pd.notna(row[col]),
                f"Cot BHXH/BHYT/BHTN/BHBNN bi thieu du lieu o dong thang moi upload (cot {col}).",
            )

    # ------------------------------------------------------------------
    # TEST CASE 4: aggregate report (Report 3) + carry-forward
    # ------------------------------------------------------------------
    def test_4_aggregate_report_and_carry_forward(self):
        self.assertIsNotNone(type(self)._upload_response, "TEST CASE 2 chua chay thanh cong truoc test nay.")
        carry_forward_count = type(self)._upload_response.get("carry_forward_count", 0)
        self.assertEqual(
            carry_forward_count, len(CARRY_FORWARD_EMP_IDS),
            f"Ky vong {len(CARRY_FORWARD_EMP_IDS)} ban ghi carry-forward, thuc te {carry_forward_count}.",
        )

        prev_resp = requests.get(
            f"{BACKEND_URL}/export-report-3", params={"month": PREV_MONTH, "year": SAFE_TEST_YEAR}, timeout=30
        )
        self.assertEqual(prev_resp.status_code, 200)
        prev_df = _read_report_rows(prev_resp.content)
        self.assertEqual(len(prev_df), len(CARRY_FORWARD_EMP_IDS))

        new_resp = requests.get(
            f"{BACKEND_URL}/export-report-3", params={"month": UPLOAD_MONTH, "year": SAFE_TEST_YEAR}, timeout=30
        )
        self.assertEqual(new_resp.status_code, 200)
        new_df = _read_report_rows(new_resp.content)

        # None of the uploaded employees are Active (TS/KL/OM/NV), so every
        # Active row in the new month must come from carry-forward.
        self.assertEqual(
            len(new_df),
            len(prev_df),
            f"So nhan vien Active thang {UPLOAD_MONTH}/{SAFE_TEST_YEAR} ({len(new_df)}) khac thang truoc "
            f"({len(prev_df)}) -- carry-forward co the da khong chay dung.",
        )
        new_emp_ids = {str(int(v)) if isinstance(v, float) else str(v) for v in new_df[1]}
        self.assertEqual(new_emp_ids, set(CARRY_FORWARD_EMP_IDS))

    # ------------------------------------------------------------------
    # TEST CASE 5: resignation / leave report (Report 4)
    # ------------------------------------------------------------------
    def test_5_resignation_report_status_labels(self):
        resp = requests.get(
            f"{BACKEND_URL}/export-report-4", params={"month": UPLOAD_MONTH, "year": SAFE_TEST_YEAR}, timeout=30
        )
        self.assertEqual(resp.status_code, 200)
        df = _read_report_rows(resp.content)
        # Columns: STT, Emp ID, Full Name, Join Date, Birth Date, Social No, Social Date, Current Status
        by_emp = {str(row[1]).strip(): str(row[7]).strip() for _, row in df.iterrows()}

        for emp_id, expected_code in UPLOAD_EMP_STATUS.items():
            self.assertIn(emp_id, by_emp, f"NV {emp_id} ({expected_code}) khong xuat hien trong Report 4.")
            self.assertEqual(
                by_emp[emp_id],
                expected_code,
                f"NV {emp_id}: ky vong '{expected_code}' nhung Report 4 ghi '{by_emp[emp_id]}' "
                "(co the da bi ghi de nham thanh 'Nghi viec').",
            )

        # The genuinely resigned employee in the SAME upload must show the
        # Vietnamese label, not a raw leave code -- proves the two paths don't collide.
        self.assertIn(RESIGNED_EMP_ID, by_emp, f"NV {RESIGNED_EMP_ID} (NV) khong xuat hien trong Report 4.")
        self.assertEqual(by_emp[RESIGNED_EMP_ID], "Nghỉ việc")


def main() -> None:
    suite = unittest.TestLoader().loadTestsFromTestCase(TestSystemIntegrity)
    runner = unittest.TextTestRunner(verbosity=2, resultclass=LoggingTestResult)
    print(f"Log chi tiet se duoc ghi tai: {LOG_FILE}")
    result = runner.run(suite)
    print(f"\nLog chi tiet: {LOG_FILE}")
    sys.exit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
