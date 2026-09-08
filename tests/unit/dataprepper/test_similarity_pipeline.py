import math
import os
import unittest
from unittest import mock

from dataprepper.similarity_engine import (
    CosineBand,
    CosineThresholds,
    EmbeddingBudgetExhausted,
    EmbeddingRunBudget,
    SimilarityPipeline,
    UpstageEmbeddingProvider,
)


def normalized_vector(score):
    """Return a 1,024-dimensional vector with the requested cosine to e1."""
    return [score, math.sqrt(1 - score**2)] + [0.0] * 1022


class FakeEmbeddingProvider:
    def __init__(self, vectors):
        self.vectors = vectors
        self.calls = []

    def embed(self, inputs):
        self.calls.append(inputs)
        return self.vectors


class FakeEmbeddingEntry:
    def __init__(self, embedding):
        self.embedding = embedding


class FakeEmbeddingResponse:
    def __init__(self, vectors):
        self.data = [FakeEmbeddingEntry(vector) for vector in vectors]


class FakeEmbeddingsResource:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class FakeUpstageClient:
    def __init__(self, responses):
        self.embeddings = FakeEmbeddingsResource(responses)


class RetryableProviderError(Exception):
    status_code = 429


class ExhaustedEmbeddingProvider:
    def embed(self, _inputs):
        raise EmbeddingBudgetExhausted("embedding budget exhausted")


class SimilarityPipelineTests(unittest.TestCase):
    def setUp(self):
        self.thresholds = CosineThresholds(high=0.90, ambiguous=0.80)
        self.left = {
            "title": "Alpha program notice",
            "content": "<p>문의 first@example.test 또는 010-1234-5678</p>",
        }
        self.right = {
            "vendor_initial": "TST",
            "external_key": "candidate-101",
            "title": "Beta schedule update",
            "content": "<div>different source notice</div>",
        }

    def test_fuzzy_match_auto_merges_without_embedding_call(self):
        provider = FakeEmbeddingProvider(
            [normalized_vector(0.1), normalized_vector(0.1)]
        )
        pipeline = SimilarityPipeline(self.thresholds, provider)

        decision = pipeline.decide(
            {"title": "Same title", "content": "left body"},
            {"title": "Same title", "content": "different body"},
        )

        self.assertEqual(CosineBand.AUTO_MERGE, decision.band)
        self.assertEqual("fuzzy", decision.stage)
        self.assertEqual([], provider.calls)

    def test_jaccard_match_auto_merges_without_embedding_call(self):
        provider = FakeEmbeddingProvider(
            [normalized_vector(0.1), normalized_vector(0.1)]
        )
        pipeline = SimilarityPipeline(self.thresholds, provider)

        decision = pipeline.decide(
            {"title": "First title", "content": "shared source body words"},
            {"title": "Second announcement", "content": "shared source body words"},
        )

        self.assertEqual(CosineBand.AUTO_MERGE, decision.band)
        self.assertEqual("jaccard", decision.stage)
        self.assertEqual([], provider.calls)

    def test_high_cosine_auto_merges_after_sanitized_embedding_request(self):
        provider = FakeEmbeddingProvider(
            [normalized_vector(1.0), normalized_vector(0.95)]
        )
        pipeline = SimilarityPipeline(self.thresholds, provider)

        decision = pipeline.decide(self.left, self.right)

        self.assertEqual(CosineBand.AUTO_MERGE, decision.band)
        self.assertEqual("cosine", decision.stage)
        self.assertEqual(0.95, decision.score)
        self.assertEqual(
            [
                [
                    "Alpha program notice 문의 <EMAIL> 또는 <PHONE>",
                    "Beta schedule update different source notice",
                ]
            ],
            provider.calls,
        )

    def test_ambiguous_cosine_returns_v11_similarity_metadata_without_status_intent(
        self,
    ):
        provider = FakeEmbeddingProvider(
            [normalized_vector(1.0), normalized_vector(0.85)]
        )
        pipeline = SimilarityPipeline(self.thresholds, provider)

        decision = pipeline.decide(self.left, self.right)

        self.assertEqual(CosineBand.REVIEW_CANDIDATE, decision.band)
        self.assertEqual(0.85, decision.score)
        self.assertEqual(85.0, decision.similarity_percent)
        self.assertEqual(
            {
                "similarity": {
                    "score": 85.0,
                    "vendor_initial": "TST",
                    "external_key": "candidate-101",
                }
            },
            decision.writer_metadata,
        )
        self.assertFalse(hasattr(decision, "status_intent"))

    def test_low_cosine_keeps_a_separate_candidate(self):
        provider = FakeEmbeddingProvider(
            [normalized_vector(1.0), normalized_vector(0.40)]
        )
        pipeline = SimilarityPipeline(self.thresholds, provider)

        decision = pipeline.decide(self.left, self.right)

        self.assertEqual(CosineBand.SEPARATE, decision.band)
        self.assertIsNone(decision.writer_metadata)

    def test_absent_provider_cannot_enable_a_live_embedding_call(self):
        pipeline = SimilarityPipeline(self.thresholds, provider=None)

        decision = pipeline.decide(self.left, self.right)

        self.assertEqual(CosineBand.SEPARATE, decision.band)
        self.assertEqual("embedding_disabled", decision.stage)

    def test_thresholds_require_a_valid_high_and_ambiguous_order(self):
        with self.assertRaises(ValueError):
            CosineThresholds(high=0.79, ambiguous=0.80)

    def test_upstage_provider_uses_the_documented_endpoint_client_and_model(self):
        vectors = [normalized_vector(1.0), normalized_vector(0.80)]
        client = FakeUpstageClient([FakeEmbeddingResponse(vectors)])
        factory = mock.Mock(return_value=client)
        provider = UpstageEmbeddingProvider(
            api_key="test-only-key", client_factory=factory
        )

        self.assertEqual(vectors, provider.embed(["first", "second"]))

        factory.assert_called_once_with(
            api_key="test-only-key",
            base_url="https://api.upstage.ai/v1",
            timeout=30,
            max_retries=0,
        )
        self.assertEqual(
            [{"model": "solar-embedding-2-passage", "input": ["first", "second"]}],
            client.embeddings.calls,
        )

    def test_upstage_provider_retries_only_a_transient_error_with_approved_backoff(
        self,
    ):
        vectors = [normalized_vector(1.0), normalized_vector(0.80)]
        client = FakeUpstageClient(
            [RetryableProviderError(), FakeEmbeddingResponse(vectors)]
        )
        sleeps = []
        provider = UpstageEmbeddingProvider(
            api_key="test-only-key",
            client_factory=mock.Mock(return_value=client),
            sleeper=sleeps.append,
        )

        provider.embed(["first", "second"])

        self.assertEqual([1], sleeps)
        self.assertEqual(2, len(client.embeddings.calls))

    def test_upstage_provider_fails_closed_when_the_runtime_key_is_absent(self):
        with mock.patch.dict(os.environ, {"UPSTAGE_API_KEY": ""}, clear=False):
            with self.assertRaises(ValueError):
                UpstageEmbeddingProvider(client_factory=mock.Mock())

    def test_provider_counts_retries_against_the_approved_run_text_budget(self):
        vectors = [normalized_vector(1.0), normalized_vector(0.80)]
        client = FakeUpstageClient(
            [RetryableProviderError(), FakeEmbeddingResponse(vectors)]
        )
        provider = UpstageEmbeddingProvider(
            api_key="test-only-key",
            client_factory=mock.Mock(return_value=client),
            sleeper=lambda _seconds: None,
            budget=EmbeddingRunBudget(max_texts=3),
        )

        with self.assertRaises(EmbeddingBudgetExhausted):
            provider.embed(["first", "second"])

        self.assertEqual(1, len(client.embeddings.calls))

    def test_budget_exhaustion_keeps_a_separate_normal_candidate(self):
        pipeline = SimilarityPipeline(self.thresholds, ExhaustedEmbeddingProvider())

        decision = pipeline.decide(self.left, self.right)

        self.assertEqual(CosineBand.SEPARATE, decision.band)
        self.assertEqual("embedding_budget_exhausted", decision.stage)
        self.assertIsNone(decision.writer_metadata)


if __name__ == "__main__":
    unittest.main()
