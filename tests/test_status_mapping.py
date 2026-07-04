import unittest

import pandas as pd

from backend.main import clean_update_dataframe


class TestStatusMapping(unittest.TestCase):
    def test_upload_status_mapping_and_default_resignation_for_blank_salary(self):
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

    def test_leave_code_statuses_are_not_overridden_by_nv_logic(self):
        df = pd.DataFrame(
            [
                {"Mã NV": "E5", "Tình trạng": "TS", "Mức lương mới": "", "Tháng - năm biến động": pd.Timestamp("2026-06-01")},
                {"Mã NV": "E6", "Tình trạng": "OM", "Mức lương mới": "", "Tháng - năm biến động": pd.Timestamp("2026-06-01")},
                {"Mã NV": "E7", "Tình trạng": "KL", "Mức lương mới": "", "Tháng - năm biến động": pd.Timestamp("2026-06-01")},
                {"Mã NV": "E8", "Tình trạng": "ST", "Mức lương mới": "", "Tháng - năm biến động": pd.Timestamp("2026-06-01")},
            ]
        )

        cleaned = clean_update_dataframe(df)

        for emp_id in ["E5", "E6", "E7", "E8"]:
            self.assertIn(cleaned.loc[cleaned["emp_id"] == emp_id, "status_in_month"].iloc[0], {"TS", "OM", "KL", "ST"})


if __name__ == "__main__":
    unittest.main()
