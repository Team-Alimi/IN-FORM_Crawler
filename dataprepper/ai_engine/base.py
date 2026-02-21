import json
import re
import time
from datetime import datetime
from openai import OpenAI
from config import UPSTAGE_AI_API_KEY
from common.logger import log_status
from .classifier import ClassificationRules
from .date_extractor import DateExtractionRules

class AI:
    """AI 통합 분석기 (Upstage Solar Pro 3)"""

    def __init__(self):
        if not UPSTAGE_AI_API_KEY:
            log_status("AI", "API Key 없음. 비활성화.", "WARN"); self.client = None; return

        self.client = OpenAI(
            api_key=UPSTAGE_AI_API_KEY, 
            base_url="https://api.upstage.ai/v1"
        )
        self.model = "solar-pro3"

    def process(self, articles):
        """배치 분석 실행"""
        if not self.client: return articles
        log_status("AI", f"분석 시작 ({len(articles)}건) - Solar Pro 3", "START")
        for a in articles:
            self._analyze(a); time.sleep(1)
        return articles

    def _analyze(self, a):
        """단일 분석 및 데이터 업데이트"""
        tit, cnt = a.get('title', ''), a.get('content', '')
        if len(cnt) > 3000: cnt = cnt[:2000] + "\n\n...(중략)...\n\n" + cnt[-1000:]
        
        c_at = a.get('created_at', datetime.now().strftime('%Y-%m-%d'))
        prompt = f"""
        University Notice Assistant.
        {ClassificationRules.get_prompt()}
        {DateExtractionRules.get_prompt(c_at)}
        Title: {tit} \n Content: {cnt}
        [OUTPUT FORMAT & STOP RULE (CRITICAL)]
        You MUST return ONLY a valid JSON object in the exact format below:
        {
            "category_id": <int 1~4>,
            "start_date": "<YYYY-MM-DD>" or null,
            "due_date": "<YYYY-MM-DD>" or null
        }
        Do NOT wrap the JSON in markdown blocks (e.g., ```json).
        Do NOT output any additional text, explanations, or trailing whitespace.
        STOP GENERATING IMMEDIATELY after the closing brace '}}'.
        """
        
        try:
            resp = self.client.chat.completions.create(
                model=self.model, 
                messages=[{"role":"user", "content":prompt}], 
                temperature=0, 
                response_format={"type":"json_object"}
            )
            raw_res = resp.choices[0].message.content.strip()
            res = json.loads(re.sub(r"^```json|```$", "", raw_res))
            
            if res.get('category_id') is not None:
                a['category_id'] = res['category_id']
            a['start_date'] = res.get('start_date')
            a['due_date'] = res.get('due_date')
            
            log_status("AI", f"성공: {tit[:15]}...", "SUCCESS")
        except Exception as e:
            log_status("AI", f"실패 ({tit[:15]}...): {e}", "ERROR")
