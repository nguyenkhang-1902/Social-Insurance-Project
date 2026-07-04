import unittest

import pandas as pd

from backend.main import _sanitize_history_record
from backend.models import PayrollHistory


class TestHistorySanitization(unittest.TestCase):
    def test_sanitize_history_record_converts_nan_to_none_and_ints(self):
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


if __name__ == "__main__":
    unittest.main()
