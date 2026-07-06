import io
import os
import sys
import unittest
from pathlib import Path

import pandas as pd
from fastapi import UploadFile
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR / "Code") not in sys.path:
    sys.path.insert(0, str(ROOT_DIR / "Code"))

from database import backup_database_file
from main import (
    _apply_carry_forward_logic,
    _delete_monthly_history,
    _extract_month_year_from_upload,
    _replace_monthly_history,
    _sanitize_history_record,
    _should_overwrite_month,
    clean_update_dataframe,
)
from models import Base, Employee, PayrollHistory
from etl_scripts.seed_data import build_history_records


class TestPortableWorkflow(unittest.TestCase):
    def test_upload_extraction_from_k6_date(self):
        rows = 10
        cols = 11
        data = [[None] * cols for _ in range(rows)]
        data[5][10] = pd.Timestamp("2026-06-01")
        df = pd.DataFrame(data)
        upload_file = self._make_upload_file_from_excel(df)

        month, year = _extract_month_year_from_upload(upload_file)

        self.assertEqual(month, 6)
        self.assertEqual(year, 2026)

    def test_status_mapping_and_default_resignation(self):
        df = pd.DataFrame(
            [
                {"Mã NV": "E1", "Tình trạng": "TS", "Mức lương mới": "", "Tháng - năm biến động": pd.Timestamp("2026-06-01")},
                {"Mã NV": "E2", "Tình trạng": "resignation", "Mức lương mới": "", "Tháng - năm biến động": pd.Timestamp("2026-06-01")},
                {"Mã NV": "E3", "Tình trạng": "", "Mức lương mới": "", "Tháng - năm biến động": pd.Timestamp("2026-06-01")},
                {"Mã NV": "E4", "Tình trạng": "", "Mức lương mới": "15000000", "Tháng - năm biến động": pd.Timestamp("2026-06-01")},
            ]
        )

        cleaned = clean_update_dataframe(df)

        self.assertEqual(cleaned.loc[cleaned["emp_id"] == "E1", "status_in_month"].iloc[0], "TS")
        self.assertEqual(cleaned.loc[cleaned["emp_id"] == "E2", "status_in_month"].iloc[0], "NV")
        self.assertEqual(cleaned.loc[cleaned["emp_id"] == "E3", "status_in_month"].iloc[0], "NV")
        self.assertEqual(cleaned.loc[cleaned["emp_id"] == "E4", "status_in_month"].iloc[0], "Active")

    def test_carry_forward_creates_expected_records(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        session = Session(engine)
        try:
            prior_record = PayrollHistory(
                emp_id="E1",
                record_month=5,
                record_year=2026,
                base_salary=15000000.0,
                status_in_month="Active",
            )
            resigned_record = PayrollHistory(
                emp_id="E2",
                record_month=5,
                record_year=2026,
                base_salary=0.0,
                status_in_month="NV",
            )
            session.add_all([prior_record, resigned_record])
            session.commit()

            created_records = _apply_carry_forward_logic(
                session,
                target_month=6,
                target_year=2026,
                uploaded_emp_ids={"E3"},
            )

            self.assertEqual(len(created_records), 2)
            created_by_emp_id = {record.emp_id: record for record in created_records}
            self.assertIn("E1", created_by_emp_id)
            self.assertIn("E2", created_by_emp_id)
        finally:
            session.close()
            engine.dispose()

    def test_history_sanitization(self):
        record = PayrollHistory(
            emp_id="E1",
            record_month=float("nan"),
            record_year=float("nan"),
            base_salary=1000.0,
            status_in_month="Active",
            resign_date=float("nan"),
        )

        sanitized = _sanitize_history_record(record)

        self.assertEqual(sanitized.record_month, 0)
        self.assertEqual(sanitized.record_year, 0)
        self.assertIsNone(sanitized.resign_date)

    def test_seed_imputation_marks_resignation_after_gap(self):
        long_frame = pd.DataFrame(
            [
                {"emp_id": "E1", "full_name": "Test", "join_date": None, "birth_date": None, "social_no": None, "social_date": None, "month": pd.Timestamp("2023-01-01"), "raw_value": 1000000, "record_month": 1, "record_year": 2023},
                {"emp_id": "E1", "full_name": "Test", "join_date": None, "birth_date": None, "social_no": None, "social_date": None, "month": pd.Timestamp("2023-02-01"), "raw_value": 1000000, "record_month": 2, "record_year": 2023},
                {"emp_id": "E1", "full_name": "Test", "join_date": None, "birth_date": None, "social_no": None, "social_date": None, "month": pd.Timestamp("2023-03-01"), "raw_value": None, "record_month": 3, "record_year": 2023},
                {"emp_id": "E1", "full_name": "Test", "join_date": None, "birth_date": None, "social_no": None, "social_date": None, "month": pd.Timestamp("2023-04-01"), "raw_value": None, "record_month": 4, "record_year": 2023},
            ]
        )

        employees, history = build_history_records(long_frame)

        self.assertEqual(len(employees), 1)
        self.assertEqual(employees[0].current_status, "Resigned")
        self.assertEqual(len(history), 3)
        self.assertEqual(history[-1].status_in_month, "Resigned")

    def test_seed_imputation_second_employee_blank_run_no_index_error(self):
        # Regression test for a real bug found while seeding the full 2009-2025
        # master file (~5934 employees): the blank-run loop used
        # `emp_frame.index[row_idx]` to address keep_mask/drop_mask, but
        # row_idx from `emp_frame.iterrows()` is already the row LABEL in the
        # full long_frame, not a position within the employee's own subset.
        # For any employee that isn't first in the groupby iteration order,
        # their row labels start well above 0, so `emp_frame.index[row_idx]`
        # either raised IndexError (e.g. "index 431 is out of bounds for axis
        # 0 with size 216") or, worse, silently masked the wrong row. E1 below
        # occupies row labels 0-4; E2's blank run then uses labels 5-7, which
        # are out of bounds for E2's own 3-row index -- this must not raise.
        long_frame = pd.DataFrame(
            [
                {"emp_id": "E1", "full_name": "Test1", "join_date": None, "birth_date": None, "social_no": None, "social_date": None, "month": pd.Timestamp("2023-01-01"), "raw_value": 1000000, "record_month": 1, "record_year": 2023},
                {"emp_id": "E1", "full_name": "Test1", "join_date": None, "birth_date": None, "social_no": None, "social_date": None, "month": pd.Timestamp("2023-02-01"), "raw_value": 1000000, "record_month": 2, "record_year": 2023},
                {"emp_id": "E1", "full_name": "Test1", "join_date": None, "birth_date": None, "social_no": None, "social_date": None, "month": pd.Timestamp("2023-03-01"), "raw_value": 1000000, "record_month": 3, "record_year": 2023},
                {"emp_id": "E1", "full_name": "Test1", "join_date": None, "birth_date": None, "social_no": None, "social_date": None, "month": pd.Timestamp("2023-04-01"), "raw_value": 1000000, "record_month": 4, "record_year": 2023},
                {"emp_id": "E1", "full_name": "Test1", "join_date": None, "birth_date": None, "social_no": None, "social_date": None, "month": pd.Timestamp("2023-05-01"), "raw_value": 1000000, "record_month": 5, "record_year": 2023},
                {"emp_id": "E2", "full_name": "Test2", "join_date": None, "birth_date": None, "social_no": None, "social_date": None, "month": pd.Timestamp("2023-01-01"), "raw_value": 2000000, "record_month": 1, "record_year": 2023},
                {"emp_id": "E2", "full_name": "Test2", "join_date": None, "birth_date": None, "social_no": None, "social_date": None, "month": pd.Timestamp("2023-02-01"), "raw_value": None, "record_month": 2, "record_year": 2023},
                {"emp_id": "E2", "full_name": "Test2", "join_date": None, "birth_date": None, "social_no": None, "social_date": None, "month": pd.Timestamp("2023-03-01"), "raw_value": None, "record_month": 3, "record_year": 2023},
            ]
        )

        # Must not raise IndexError.
        employees, history = build_history_records(long_frame)

        employees_by_id = {emp.emp_id: emp for emp in employees}
        self.assertEqual(employees_by_id["E1"].current_status, "Active")
        self.assertEqual(employees_by_id["E2"].current_status, "Resigned")

        e2_history = sorted(
            [h for h in history if h.emp_id == "E2"],
            key=lambda h: (h.record_year, h.record_month),
        )
        # Jan kept (value), Feb dropped (blank, superseded), Mar kept (blank -> resignation)
        self.assertEqual(len(e2_history), 2)
        self.assertEqual(e2_history[0].record_month, 1)
        self.assertEqual(e2_history[1].record_month, 3)
        self.assertEqual(e2_history[1].status_in_month, "Resigned")

    def test_should_overwrite_month_no_hardcoded_month_bypass(self):
        # Guard against regressions of the removed "month == 6 and year == 2026"
        # hardcoded bypass. Overwrite must depend ONLY on the explicit flag / existing
        # record count -- never on which month/year is being uploaded.
        self.assertFalse(_should_overwrite_month(overwrite="false", existing_count=0))
        self.assertTrue(_should_overwrite_month(overwrite="true", existing_count=0))
        self.assertTrue(_should_overwrite_month(overwrite="false", existing_count=5))
        self.assertFalse(_should_overwrite_month(overwrite="False", existing_count=0))

        # The helper must not even accept month/year -- proves the decision cannot
        # special-case a specific month/year anymore.
        import inspect

        params = list(inspect.signature(_should_overwrite_month).parameters)
        self.assertNotIn("month", params)
        self.assertNotIn("year", params)

    def test_seed_backup_creates_snapshot_before_wipe(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_dir_path = Path(tmp_dir)
            fake_db = tmp_dir_path / "app.db"
            fake_db.write_bytes(b"fake-sqlite-content")
            backup_dir = tmp_dir_path / "backups"

            backup_path = backup_database_file(fake_db, backup_dir)

            self.assertTrue(backup_path.exists())
            self.assertEqual(backup_path.read_bytes(), b"fake-sqlite-content")
            # original file must be untouched
            self.assertTrue(fake_db.exists())
            self.assertEqual(fake_db.read_bytes(), b"fake-sqlite-content")

    def test_seed_backup_noop_when_db_missing(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_dir_path = Path(tmp_dir)
            missing_db = tmp_dir_path / "does_not_exist.db"
            backup_dir = tmp_dir_path / "backups"

            backup_path = backup_database_file(missing_db, backup_dir)

            self.assertIsNone(backup_path)
            self.assertFalse(backup_dir.exists())

    def _make_upload_file_from_excel(self, data_frame: pd.DataFrame, filename: str = "test.xlsx") -> UploadFile:
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            data_frame.to_excel(writer, index=False, header=False)
        buffer.seek(0)
        return UploadFile(filename=filename, file=io.BytesIO(buffer.read()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
