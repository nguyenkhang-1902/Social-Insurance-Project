import pandas as pd

from backend.etl_scripts.seed_data import build_history_records


def test_build_history_records_marks_resignation_after_gap():
    long_frame = pd.DataFrame(
        [
            {"emp_id": "E1", "full_name": "Test", "join_date": None, "birth_date": None, "social_no": None, "social_date": None, "month": pd.Timestamp("2023-01-01"), "raw_value": 1000000, "record_month": 1, "record_year": 2023},
            {"emp_id": "E1", "full_name": "Test", "join_date": None, "birth_date": None, "social_no": None, "social_date": None, "month": pd.Timestamp("2023-02-01"), "raw_value": 1000000, "record_month": 2, "record_year": 2023},
            {"emp_id": "E1", "full_name": "Test", "join_date": None, "birth_date": None, "social_no": None, "social_date": None, "month": pd.Timestamp("2023-03-01"), "raw_value": None, "record_month": 3, "record_year": 2023},
            {"emp_id": "E1", "full_name": "Test", "join_date": None, "birth_date": None, "social_no": None, "social_date": None, "month": pd.Timestamp("2023-04-01"), "raw_value": None, "record_month": 4, "record_year": 2023},
        ]
    )

    employees, history = build_history_records(long_frame)

    assert len(employees) == 1
    assert employees[0].current_status == "Resigned"
    assert len(history) == 3
    assert history[-1].status_in_month == "Resigned"
