import google.generativeai as genai
import json
import re
import time
from datetime import datetime
from config import GEMINI_API_KEY

from .classifier import ClassificationRules
from .date_extractor import DateExtractionRules


class AIProcessor:
    def __init__(self):
        if not GEMINI_API_KEY:
            print("⚠️ [AI] API Key가 설정되지 않았습니다.")
            self.model = None
            return

        genai.configure(api_key=GEMINI_API_KEY)
        self.model = genai.GenerativeModel('gemini-2.5-flash')

    def process_batch(self, article_list):
        """
        리스트를 받아 [분류 + 날짜추출]을 동시에 수행하고 업데이트된 리스트 반환
        """
        if not self.model: return article_list

        print(f"   🚀 [AI] 통합 분석 시작 ({len(article_list)}건) - Gemini 2.5 Flash")

        for article in article_list:
            self._analyze_single_article(article)

            # Rate Limit 방지 안전하게 4초 대기 (분당 15회 제한)
            time.sleep(4)

        return article_list

    def _analyze_single_article(self, article):
        title = article.get('title', '')
        raw_content = article.get('content', '')

        # 본문이 3000자를 넘어가면, 앞 2000자 + 뒤 1000자만 추출하여 합침
        if len(raw_content) > 3000:
            content = raw_content[:2000] + "\n\n... (중략) ...\n\n" + raw_content[-1000:]
        else:
            content = raw_content

        created_at = article.get('created_at', datetime.now().strftime('%Y-%m-%d'))

        # 두 모듈의 프롬프트를 여기서 조립합니다.
        full_prompt = f"""
        You are an expert University Notice Assistant. Perform TWO tasks.

        {ClassificationRules.get_prompt()}

        {DateExtractionRules.get_prompt(created_at)}

        [INPUT DATA]
        Title: {title}
        Content: {content}

        [OUTPUT FORMAT - JSON ONLY]
        Return a single JSON object:
        {{
            "category_id": <int>,
            "start_date": "<YYYY-MM-DD or null>",
            "due_date": "<YYYY-MM-DD or null>"
        }}
        """

        try:
            # API 호출 (1회)
            response = self.model.generate_content(full_prompt)
            result_text = response.text.strip()

            # JSON 파싱 전처리
            result_text = re.sub(r"^```json|^```", "", result_text).strip()
            result_text = re.sub(r"```$", "", result_text).strip()

            data = json.loads(result_text)

            # 데이터 주입
            article['category_id'] = data.get('category_id')
            article['start_date'] = data.get('start_date')
            article['due_date'] = data.get('due_date')

            print(f"      ✅ [OK] ID:{article['category_id']} | Due:{article['due_date']} | {title[:15]}...")

        except Exception as e:
            print(f"      ⚠️ [Fail] 분석 실패: {e}")
            # 실패 시 기존 값 유지