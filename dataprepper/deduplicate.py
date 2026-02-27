import json
import os
from config import HISTORY_DIR

class HistoryManager:
    """사이트별 수집 히스토리 관리"""

    def __init__(self, name):
        self.path = os.path.join(HISTORY_DIR, f"{name}.json")
        self.data = self._load()

    def _load(self):
        """히스토리 파일 로드 및 사전 변환"""
        if not os.path.exists(self.path): return {}
        try:
            with open(self.path, 'r', encoding='utf-8') as f:
                articles = json.load(f)
            return {a['unique_id']: a for a in articles if 'unique_id' in a}
        except: return {}

    def check(self, article):
        """기존 데이터와의 비교를 통해 신규/변경 여부 판별"""
        uid = article.get('unique_id')
        if uid not in self.data: return True, False, None
        old = self.data[uid]
        changed = (
            article['title'] != old.get('title') or 
            article['content'] != old.get('content') or
            article.get('attachments') != old.get('attachments')
        )
        return False, changed, old

    def update(self, article):
        """메모리 내 히스토리 데이터 갱신"""
        self.data[article.get('unique_id')] = article

    def save(self):
        """히스토리 데이터를 파일로 저장 및 정리"""
        out = []
        for a in self.data.values():
            a.pop('vendor_id', None); a.pop('site_name', None)
            out.append(a)
        with open(self.path, 'w', encoding='utf-8') as f:
            json.dump(out, f, ensure_ascii=False, indent=4)
