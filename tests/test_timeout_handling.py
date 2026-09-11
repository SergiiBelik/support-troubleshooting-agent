import unittest

from main import execute_tool


class TimeoutHandlingTests(unittest.TestCase):
    def test_log_search_timeout_returns_retryable_error(self):
        result = execute_tool(
            "search_logs",
            {"customer_id": "cust_timeout", "error_code": "503"}
        )

        self.assertEqual(result["ok"], False)
        self.assertEqual(result["error"]["code"], "timeout")
        self.assertTrue(result["error"]["retryable"])
        self.assertEqual(
            result["error"]["message"],
            "The backend service timed out."
        )


if __name__ == "__main__":
    unittest.main()
