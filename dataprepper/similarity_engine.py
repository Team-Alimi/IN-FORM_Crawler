import math
import os
import re
import time
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from thefuzz import fuzz

from .text_cleaner import Cleaner

# 설계 상수 (Blueprint Constants)
FUZZY_THRESHOLD = 0.85
JACCARD_THRESHOLD = 0.48
UPSTAGE_EMBEDDING_DIMENSIONS = 1024
UPSTAGE_EMBEDDING_MODEL = "solar-embedding-2-passage"
UPSTAGE_API_BASE_URL = "https://api.upstage.ai/v1"
UPSTAGE_EMBEDDING_TIMEOUT_SECONDS = 30
UPSTAGE_EMBEDDING_MAX_ATTEMPTS = 3


class CosineBand(str, Enum):
    AUTO_MERGE = "AUTO_MERGE"
    REVIEW_CANDIDATE = "REVIEW_CANDIDATE"
    SEPARATE = "SEPARATE"


@dataclass(frozen=True)
class CosineThresholds:
    """An explicitly supplied, already-approved Cosine decision band."""

    high: float
    ambiguous: float

    def __post_init__(self):
        if not all(
            isinstance(value, (int, float)) and not isinstance(value, bool)
            for value in (self.high, self.ambiguous)
        ):
            raise ValueError("Cosine thresholds must be numeric")
        if not 0.0 <= self.ambiguous <= self.high <= 1.0:
            raise ValueError("Cosine thresholds require 0 <= ambiguous <= high <= 1")


@dataclass(frozen=True)
class SimilarityDecision:
    band: CosineBand
    stage: str
    score: float | None = None
    similar_vendor_initial: str | None = None
    similar_external_key: str | None = None

    @property
    def similarity_percent(self):
        if self.score is None:
            return None
        return round(self.score * 100, 2)

    @property
    def writer_metadata(self):
        """Return only the v11/V14 duplicate-review metadata a writer may persist.

        The pure pipeline never owns backend numeric article IDs. It exposes review metadata only
        when the comparison target has a stable crawler source identity for the writer to resolve.
        """
        if (
            self.band is not CosineBand.REVIEW_CANDIDATE
            or self.similarity_percent is None
            or not isinstance(self.similar_vendor_initial, str)
            or not self.similar_vendor_initial.strip()
            or not isinstance(self.similar_external_key, str)
            or not self.similar_external_key.strip()
        ):
            return None
        return {
            "similarity": {
                "score": self.similarity_percent,
                "vendor_initial": self.similar_vendor_initial.strip(),
                "external_key": self.similar_external_key.strip(),
            },
        }


class EmbeddingProvider(Protocol):
    def embed(self, inputs: Sequence[str]) -> Sequence[Sequence[float]]: ...


class EmbeddingBudgetExhausted(RuntimeError):
    """Raised before a paid provider call would exceed the approved run budget."""


@dataclass
class EmbeddingRunBudget:
    """Run-scoped text budget. Every retry reserves the submitted text count again."""

    max_texts: int = 200
    used_texts: int = 0

    def __post_init__(self):
        if not isinstance(self.max_texts, int) or isinstance(self.max_texts, bool):
            raise ValueError("Embedding run budget must be an integer")
        if self.max_texts < 0:
            raise ValueError("Embedding run budget cannot be negative")

    def reserve(self, text_count):
        if self.used_texts + text_count > self.max_texts:
            raise EmbeddingBudgetExhausted("embedding run text budget exhausted")
        self.used_texts += text_count


class UpstageEmbeddingProvider:
    """Small, fail-closed adapter for the approved Upstage embedding endpoint."""

    _retryable_status_codes = frozenset({429, 500, 502, 503, 504})

    def __init__(self, api_key=None, client_factory=None, sleeper=None, budget=None):
        key = (api_key or os.getenv("UPSTAGE_API_KEY", "")).strip()
        if not key:
            raise ValueError("UPSTAGE_API_KEY is required for embedding")

        if client_factory is None:
            from openai import OpenAI

            client_factory = OpenAI

        self.client = client_factory(
            api_key=key,
            base_url=UPSTAGE_API_BASE_URL,
            timeout=UPSTAGE_EMBEDDING_TIMEOUT_SECONDS,
            max_retries=0,
        )
        self.sleeper = sleeper or time.sleep
        self.budget = budget or EmbeddingRunBudget()

    def embed(self, inputs):
        request_inputs = list(inputs)
        if not request_inputs or len(request_inputs) > 100:
            raise ValueError("Embedding requests require between one and 100 inputs")
        if any(
            not isinstance(value, str) or not value.strip() for value in request_inputs
        ):
            raise ValueError("Embedding inputs must be non-empty strings")

        for attempt in range(UPSTAGE_EMBEDDING_MAX_ATTEMPTS):
            try:
                self.budget.reserve(len(request_inputs))
                response = self.client.embeddings.create(
                    model=UPSTAGE_EMBEDDING_MODEL,
                    input=request_inputs,
                )
                return [item.embedding for item in response.data]
            except Exception as error:
                if (
                    attempt == UPSTAGE_EMBEDDING_MAX_ATTEMPTS - 1
                    or not self._is_retryable(error)
                ):
                    raise
                self.sleeper(2**attempt)

    @classmethod
    def _is_retryable(cls, error):
        if getattr(error, "status_code", None) in cls._retryable_status_codes:
            return True
        if isinstance(error, (ConnectionError, TimeoutError)):
            return True
        return type(error).__name__ in {"APIConnectionError", "APITimeoutError"}


class SimilarityEngine:
    """3-Step 유사도 분석 엔진"""

    @staticmethod
    def get_tokens(text):
        """텍스트에서 유의미한 토큰(단어) 추출"""
        if not text:
            return set()
        # 한글, 영문, 숫자 기준 2자 이상 단어만 추출
        words = re.findall(r"[가-힣a-zA-Z0-9]{2,}", text)
        return set(words)

    def fuzzy_match(self, title1, title2):
        """[1] 제목 간 Fuzzy 유사도 분석"""
        ratio = fuzz.token_sort_ratio(title1, title2) / 100.0
        return ratio >= FUZZY_THRESHOLD

    def get_jaccard_similarity(self, art1, art2):
        """[2] 제목+본문 통합 토큰의 Jaccard 유사도 분석"""
        set1 = self.get_tokens(art1.get("norm_title", "")) | self.get_tokens(
            art1.get("content_raw", "")
        )
        set2 = self.get_tokens(art2.get("norm_title", "")) | self.get_tokens(
            art2.get("content_raw", "")
        )

        if not set1 or not set2:
            return 0.0

        union = len(set1 | set2)
        intersection = len(set1 & set2)
        return intersection / union

    def jaccard_match(self, art1, art2):
        """[2] Jaccard 임계값(0.48) 기반 자동 통합 여부 판별"""
        return self.get_jaccard_similarity(art1, art2) >= JACCARD_THRESHOLD


class SimilarityPipeline:
    """Pure Fuzzy → Jaccard → embedding/Cosine candidate classifier.

    It emits only a decision intent; it neither writes to the database nor mutates input articles.
    A caller must provide an approved threshold artifact and provider before embedding can run.
    """

    def __init__(
        self, thresholds: CosineThresholds, provider: EmbeddingProvider | None
    ):
        self.thresholds = thresholds
        self.provider = provider
        self.engine = SimilarityEngine()
        self.cleaner = Cleaner()

    def decide(self, left, right):
        left_similarity = self._similarity_article(left)
        right_similarity = self._similarity_article(right)

        if self.engine.fuzzy_match(
            left_similarity["norm_title"], right_similarity["norm_title"]
        ):
            return SimilarityDecision(CosineBand.AUTO_MERGE, "fuzzy")

        if self.engine.jaccard_match(left_similarity, right_similarity):
            return SimilarityDecision(CosineBand.AUTO_MERGE, "jaccard")

        if self.provider is None:
            return SimilarityDecision(CosineBand.SEPARATE, "embedding_disabled")

        inputs = [
            self.cleaner.prepare_embedding_input(
                left.get("title", ""), left.get("content", "")
            ),
            self.cleaner.prepare_embedding_input(
                right.get("title", ""), right.get("content", "")
            ),
        ]
        try:
            score = self._cosine_similarity(self.provider.embed(inputs))
        except EmbeddingBudgetExhausted:
            return SimilarityDecision(CosineBand.SEPARATE, "embedding_budget_exhausted")

        if score >= self.thresholds.high:
            return SimilarityDecision(CosineBand.AUTO_MERGE, "cosine", score)
        if score >= self.thresholds.ambiguous:
            return SimilarityDecision(
                CosineBand.REVIEW_CANDIDATE,
                "cosine",
                score,
                right.get("vendor_initial"),
                right.get("external_key"),
            )
        return SimilarityDecision(CosineBand.SEPARATE, "cosine", score)

    @staticmethod
    def _similarity_article(article):
        return {
            "norm_title": article.get("norm_title", article.get("title", "")) or "",
            "content_raw": article.get("content_raw", article.get("content", "")) or "",
        }

    @staticmethod
    def _cosine_similarity(vectors):
        if len(vectors) != 2:
            raise ValueError("Embedding comparison requires exactly two vectors")

        left, right = vectors
        if (
            len(left) != UPSTAGE_EMBEDDING_DIMENSIONS
            or len(right) != UPSTAGE_EMBEDDING_DIMENSIONS
        ):
            raise ValueError(
                "Embedding vectors must match the approved 1,024 dimensions"
            )
        if not all(
            math.isfinite(value) for vector in (left, right) for value in vector
        ):
            raise ValueError("Embedding vectors must contain only finite values")

        left_norm = math.sqrt(sum(value * value for value in left))
        right_norm = math.sqrt(sum(value * value for value in right))
        if not left_norm or not right_norm:
            raise ValueError("Embedding vectors must be non-zero")

        score = sum(a * b for a, b in zip(left, right)) / (left_norm * right_norm)
        return max(-1.0, min(1.0, score))
