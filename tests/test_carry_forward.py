import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.main import _apply_carry_forward_logic, _delete_monthly_history, _replace_monthly_history
from backend.models import Base, Employee, PayrollHistory


class TestCarryForwardLogic(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)

    def tearDown(self):
        self.session.close()

    def test_carry_forward_creates_active_rows_for_missing_prior_month_employees(self):
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
        self.session.add_all([prior_record, resigned_record])
        self.session.commit()

        created_records = _apply_carry_forward_logic(
            self.session,
            target_month=6,
            target_year=2026,
            uploaded_emp_ids={"E3"},
        )

        self.assertEqual(len(created_records), 2)
        created_by_emp_id = {record.emp_id: record for record in created_records}
        self.assertIn("E1", created_by_emp_id)
        self.assertIn("E2", created_by_emp_id)
        self.assertEqual(created_by_emp_id["E1"].record_month, 6)
        self.assertEqual(created_by_emp_id["E1"].record_year, 2026)
        self.assertEqual(created_by_emp_id["E1"].base_salary, 15000000.0)
        self.assertEqual(created_by_emp_id["E1"].status_in_month, "Active")
        self.assertEqual(created_by_emp_id["E2"].status_in_month, "NV")

    def test_replace_monthly_history_removes_existing_rows_for_the_target_month(self):
        existing_rows = [
            PayrollHistory(emp_id="E1", record_month=6, record_year=2026, base_salary=1000000.0, status_in_month="Active"),
            PayrollHistory(emp_id="E2", record_month=6, record_year=2026, base_salary=500000.0, status_in_month="NV"),
        ]
        self.session.add_all(existing_rows)
        self.session.commit()

        deleted_count = _replace_monthly_history(self.session, month=6, year=2026)

        self.assertEqual(deleted_count, 2)
        self.assertEqual(
            self.session.query(PayrollHistory)
            .filter(PayrollHistory.record_month == 6)
            .filter(PayrollHistory.record_year == 2026)
            .count(),
            0,
        )

    def test_delete_monthly_history_removes_only_target_month_rows(self):
        rows = [
            PayrollHistory(emp_id="E1", record_month=5, record_year=2026, base_salary=1000000.0, status_in_month="Active"),
            PayrollHistory(emp_id="E2", record_month=6, record_year=2026, base_salary=500000.0, status_in_month="TS"),
            PayrollHistory(emp_id="E3", record_month=6, record_year=2025, base_salary=600000.0, status_in_month="Active"),
        ]
        self.session.add_all(rows)
        self.session.commit()

        deleted_count = _delete_monthly_history(self.session, month=6, year=2026)

        self.assertEqual(deleted_count, 1)
        remaining = (
            self.session.query(PayrollHistory)
            .filter(PayrollHistory.record_month == 6)
            .filter(PayrollHistory.record_year == 2026)
            .count()
        )
        self.assertEqual(remaining, 0)

    def test_carry_forward_preserves_status_for_employee_and_history_record(self):
        employee = Employee(emp_id="E3", full_name="Employee 3", current_status="TS", current_salary=1000000.0)
        prior_record = PayrollHistory(
            emp_id="E3",
            record_month=5,
            record_year=2026,
            base_salary=1000000.0,
            status_in_month="TS",
        )
        self.session.add_all([employee, prior_record])
        self.session.commit()

        created_records = _apply_carry_forward_logic(
            self.session,
            target_month=6,
            target_year=2026,
            uploaded_emp_ids=set(),
        )

        self.assertEqual(len(created_records), 1)
        self.assertEqual(created_records[0].status_in_month, "TS")
        self.assertEqual(created_records[0].base_salary, 1000000.0)

        refreshed_employee = self.session.get(Employee, "E3")
        self.assertEqual(refreshed_employee.current_status, "TS")

    def test_carry_forward_copies_prior_month_status_and_salary_for_missing_employees(self):
        prior_record = PayrollHistory(
            emp_id="E4",
            record_month=5,
            record_year=2026,
            base_salary=2500000.0,
            status_in_month="OM",
        )
        self.session.add(prior_record)
        self.session.commit()

        created_records = _apply_carry_forward_logic(
            self.session,
            target_month=6,
            target_year=2026,
            uploaded_emp_ids={"E1"},
        )

        self.assertEqual(len(created_records), 1)
        self.assertEqual(created_records[0].emp_id, "E4")
        self.assertEqual(created_records[0].record_month, 6)
        self.assertEqual(created_records[0].record_year, 2026)
        self.assertEqual(created_records[0].base_salary, 2500000.0)
        self.assertEqual(created_records[0].status_in_month, "OM")


if __name__ == "__main__":
    unittest.main()
