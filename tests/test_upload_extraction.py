import io
import unittest

import pandas as pd
from fastapi import UploadFile

from backend.main import _extract_month_year_from_upload


def _make_upload_file_from_excel(data_frame: pd.DataFrame, filename: str = "test.xlsx") -> UploadFile:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        data_frame.to_excel(writer, index=False, header=False)
    buffer.seek(0)
    return UploadFile(filename=filename, file=io.BytesIO(buffer.read()))


class TestUploadExtraction(unittest.TestCase):
    def test_extract_month_year_from_upload_k6_date(self):
        rows = 10
        cols = 11
        data = [[None] * cols for _ in range(rows)]
        data[5][10] = pd.Timestamp("2026-06-01")
        df = pd.DataFrame(data)
        upload_file = _make_upload_file_from_excel(df)

        month, year = _extract_month_year_from_upload(upload_file)

        self.assertEqual(month, 6)
        self.assertEqual(year, 2026)

    def test_extract_month_year_from_upload_header_keyword_column(self):
        rows = 10
        cols = 11
        data = [[None] * cols for _ in range(rows)]
        data[1][10] = "Tháng - Năm"
        data[2][10] = "06-2026"
        df = pd.DataFrame(data)
        upload_file = _make_upload_file_from_excel(df)

        month, year = _extract_month_year_from_upload(upload_file)

        self.assertEqual(month, 6)
        self.assertEqual(year, 2026)


if __name__ == "__main__":
    unittest.main()
