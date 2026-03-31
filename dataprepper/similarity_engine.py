import re
from thefuzz import fuzz

# 설계 상수 (Blueprint Constants)
FUZZY_THRESHOLD = 0.85
JACCARD_THRESHOLD = 0.48

class SimilarityEngine:
    """Sequential 2-Step 유사도 분석 엔진"""

    @staticmethod
    def get_tokens(text):
        """텍스트에서 유의미한 토큰(단어) 추출"""
        if not text: return set()
        # 한글, 영문, 숫자 기준 2자 이상 단어만 추출
        words = re.findall(r'[가-힣a-zA-Z0-9]{2,}', text)
        return set(words)

    def fuzzy_match(self, title1, title2):
        """제목 간 Fuzzy 유사도 분석"""
        ratio = fuzz.token_sort_ratio(title1, title2) / 100.0
        return ratio >= FUZZY_THRESHOLD

    def jaccard_match(self, art1, art2):
        """제목+본문 통합 토큰 Jaccard 분석"""
        set1 = self.get_tokens(art1.get('norm_title', '')) | self.get_tokens(art1.get('content_raw', ''))
        set2 = self.get_tokens(art2.get('norm_title', '')) | self.get_tokens(art2.get('content_raw', ''))
        
        if not set1 or not set2: return False
        
        union = len(set1 | set2)
        intersection = len(set1 & set2)
        sim = intersection / union
        return sim >= JACCARD_THRESHOLD
