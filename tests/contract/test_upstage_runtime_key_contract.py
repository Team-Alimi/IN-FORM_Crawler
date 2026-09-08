import importlib
import os
import unittest
from unittest import mock

import config
from dataprepper.ai_engine import base


class UpstageRuntimeKeyContractTests(unittest.TestCase):
    def tearDown(self):
        importlib.reload(config)
        importlib.reload(base)

    def test_ai_client_uses_only_the_approved_upstage_api_key_environment_variable(
        self,
    ):
        with mock.patch.dict(
            os.environ,
            {"UPSTAGE_API_KEY": "test-only-key", "UPSTAGE_AI_API_KEY": "legacy-key"},
            clear=False,
        ):
            importlib.reload(config)
            importlib.reload(base)

            with mock.patch.object(base, "OpenAI") as openai:
                base.AI()

        openai.assert_called_once_with(
            api_key="test-only-key", base_url="https://api.upstage.ai/v1"
        )


if __name__ == "__main__":
    unittest.main()
