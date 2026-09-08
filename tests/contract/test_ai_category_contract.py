import unittest
from unittest.mock import Mock, patch

from config import (
    CANONICAL_CATEGORY_CODES,
    category_code_allows_write,
    normalize_category_code,
)
from dataprepper.ai_engine.base import AI
from dataprepper.ai_engine.classifier import ClassificationRules

EXPECTED_CATEGORY_CODES = {
    "ACADEMIC",
    "ACTIVITY",
    "CAREER",
    "CERTIFICATION",
    "CONTEST",
    "EVENT",
    "FOREIGN",
    "LECTURE",
    "RESEARCH",
    "SCHOLARSHIP",
    "VOLUNTEER",
    "ETC",
}


class AICategoryContractTests(unittest.TestCase):
    def _analyzer_for(self, category_code):
        analyzer = AI.__new__(AI)
        analyzer.client = object()
        analyzer._call_api_with_retry = Mock(
            return_value={
                "category_code": category_code,
                "start_date": None,
                "due_date": None,
            }
        )
        return analyzer

    def test_only_approved_canonical_codes_are_valid(self):
        self.assertEqual(set(CANONICAL_CATEGORY_CODES), EXPECTED_CATEGORY_CODES)

        for category_code in EXPECTED_CATEGORY_CODES:
            self.assertEqual(normalize_category_code(category_code), category_code)
            self.assertTrue(category_code_allows_write(category_code))

        for legacy_or_unknown in (0, 1, "1", "EXCLUDE", "SEMINAR", "UNKNOWN", None):
            with self.subTest(legacy_or_unknown=legacy_or_unknown):
                with self.assertRaises(ValueError):
                    normalize_category_code(legacy_or_unknown)

    def test_classifier_prompt_requests_category_code_not_numeric_category_id(self):
        prompt = ClassificationRules.get_prompt()

        self.assertIn("category_code", prompt)
        self.assertNotIn("Category ID", prompt)
        for category_code in EXPECTED_CATEGORY_CODES:
            self.assertIn(category_code, prompt)

    def test_valid_code_is_emitted_as_category_code_without_legacy_numeric_id(self):
        article = {
            "title": "Contest",
            "content": "Contest body",
            "created_at": "2026-01-15",
        }
        analyzer = self._analyzer_for("CONTEST")

        with patch("dataprepper.ai_engine.base.log_status"):
            processed = analyzer.process([article])

        self.assertEqual(processed, [article])
        self.assertEqual(article["category_code"], "CONTEST")
        self.assertNotIn("category_id", article)

    def test_etc_result_remains_a_write_candidate_without_numeric_category_id(self):
        article = {
            "title": "Ignore",
            "content": "Ignore body",
            "created_at": "2026-01-15",
        }
        analyzer = self._analyzer_for("ETC")

        with patch("dataprepper.ai_engine.base.log_status"):
            processed = analyzer.process([article])

        self.assertEqual(processed, [article])
        self.assertEqual(article["category_code"], "ETC")
        self.assertNotIn("category_id", article)


if __name__ == "__main__":
    unittest.main()
