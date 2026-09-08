import unittest
from unittest.mock import patch

from common.utils import is_excluded


class SourcePreFilterTests(unittest.TestCase):
    def test_keyword_filter_rejects_only_before_ai_category_classification(self):
        with patch.dict(
            "common.utils.KEYWORD_CATEGORIES", {0: ["system-only"]}, clear=True
        ):
            self.assertTrue(is_excluded("System-only maintenance"))
            self.assertFalse(is_excluded("Student scholarship notice"))


if __name__ == "__main__":
    unittest.main()
