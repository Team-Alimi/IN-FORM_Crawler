import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from openai import OpenAI
from tenacity import RetryError, retry, stop_after_attempt, wait_exponential

from common.logger import log_status
from config import UPSTAGE_API_KEY, category_code_allows_write, normalize_category_code

from .classifier import ClassificationRules
from .date_extractor import DateExtractionRules


class AI:
    """Upstage Solar Pro 3 기반 AI 통합 분석기"""

    def __init__(self):
        """API 클라이언트 초기화 및 모델 설정"""
        if not UPSTAGE_API_KEY:
            log_status("AI", "API Key 없음. 비활성화.", "WARN")
            self.client = None
            return

        self.client = OpenAI(
            api_key=UPSTAGE_API_KEY, base_url="https://api.upstage.ai/v1"
        )
        self.model = "solar-pro3"

    def process(self, articles):
        """병렬 처리를 통한 배치 분석 실행"""
        if not self.client or not articles:
            return articles
        log_status(
            "AI", f"분석 시작 ({len(articles)}건) - Solar Pro 3 (Parallel)", "START"
        )

        with ThreadPoolExecutor(max_workers=3) as executor:
            return [
                article for article in executor.map(self._analyze, articles) if article
            ]

    @retry(
        stop=stop_after_attempt(6), wait=wait_exponential(multiplier=1, min=2, max=20)
    )
    def _call_api_with_retry(self, system_prompt, user_content):
        """API 호출 및 중괄호 기반 JSON 추출 (재시도 포함)"""
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=0,
            max_tokens=1500,
            response_format={"type": "json_object"},
        )

        content = resp.choices[0].message.content
        if not content or not content.strip():
            raise ValueError("Empty response")

        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        match = re.search(r"(\{.*\})", content, re.DOTALL)
        if not match:
            raise ValueError("No JSON found in response")

        raw_json = match.group(1)

        try:
            return json.loads(raw_json)
        except json.JSONDecodeError:
            # 1. 꼬리 쉼표(Trailing comma) 제거 시도
            cleaned = re.sub(r",(\s*[\}\]])", r"\1", raw_json)
            try:
                return json.loads(cleaned)
            except:
                pass

            # 2. 끝이 짤렸을 경우 강제로 중괄호 닫기 시도
            for closer in ["}", '"}', "null}"]:
                try:
                    return json.loads(cleaned.rstrip() + closer)
                except:
                    continue

            raise ValueError("JSON 파싱 및 복구 실패")

    def _analyze(self, article):
        """단일 게시글 분석 및 데이터 필드 업데이트"""
        tit, cnt = article.get("title", ""), article.get("content", "")

        if len(cnt) > 3000:
            cnt = cnt[:2000] + "\n\n...(중략)...\n\n" + cnt[-1000:]

        c_at = article.get("created_at", datetime.now().strftime("%Y-%m-%d"))

        system_prompt = f"""
                You are an Expert Data Classifier and Information Extractor specializing in university notices.
                {ClassificationRules.get_prompt()}
                {DateExtractionRules.get_prompt(c_at)}

                [CRITICAL INSTRUCTION]
                1. Extract category_code, start_date, and due_date.
                2. Briefly write your thought process in the 'reasoning' key FIRST.

                [OUTPUT FORMAT & STOP RULE]
                You MUST return ONLY a valid JSON object with EXACTLY these 4 keys:
                {{
                    "reasoning": "<Write 1-2 short sentences explaining classification and date extraction step-by-step>",
                    "category_code": "<one canonical v10 category code>",
                    "start_date": "<YYYY-MM-DD>" or null,
                    "due_date": "<YYYY-MM-DD>" or null
                }}
                """

        user_content = f"TITLE: {tit}\nCONTENT: {cnt}"

        try:
            res = self._call_api_with_retry(system_prompt, user_content)

            category_code = normalize_category_code(res.get("category_code"))
            if not category_code_allows_write(category_code):
                return None

            article["category_code"] = category_code
            article["start_date"] = res.get("start_date")
            article["due_date"] = res.get("due_date")

            log_status("AI", f"성공: {tit[:15]}...", "SUCCESS")
            return article
        except RetryError as error:
            log_status("AI", f"재시도 실패 (6회): {tit[:15]}...", "ERROR")
            raise error
        except Exception as e:
            log_status("AI", f"오류 ({tit[:15]}...): {e}", "ERROR")
            raise
