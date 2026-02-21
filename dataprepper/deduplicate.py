import json
import os
from config import HISTORY_DIR

class HistoryManager:
    """사이트별 로컬 수집 히스토리를 관리함."""

    def __init__(self, site_name):
        self.site_name = site_name
        self.history_path = os.path.join(HISTORY_DIR, f"{self.site_name}.json")
        self.history_map = self._load_history_file()

    def _load_history_file(self):
        """히스토리 파일 로딩"""
        if not os.path.exists(self.history_path): return {}
        try:
            with open(self.history_path, 'r', encoding='utf-8') as f:
                data_list = json.load(f)
            return {article['unique_id']: article for article in data_list if 'unique_id' in article}
        except: return {}

    def compare_with_history(self, article):
        """기존 데이터와 현재 수집 데이터를 비교하여 변경 여부 확인"""
        unique_id = article.get('unique_id')
        if unique_id not in self.history_map: return True, False, None
        
        old_article = self.history_map[unique_id]
        # 제목, 본문, 또는 첨부파일(이미지)이 변경되었는지 확인
        is_changed = (
            article['title'] != old_article.get('title') or 
            article['content'] != old_article.get('content') or
            article.get('attachments') != old_article.get('attachments')
        )
        return False, is_changed, old_article

    def update_local_history(self, article):
        """메모리 히스토리 맵 업데이트"""
        self.history_map[article.get('unique_id')] = article

    def sync_history_file(self):
        """히스토리 파일 저장 및 동기화 (맵 필드 제외)"""
        all_data = []
        for article in self.history_map.values():
            # 저장 전에 맵 형태 필드가 있다면 제거 (클린 저장)
            article.pop('vendor_urls_map', None)
            article.pop('vendor_id', None)
            article.pop('site_name', None)
            all_data.append(article)
            
        with open(self.history_path, 'w', encoding='utf-8') as f:
            json.dump(all_data, f, ensure_ascii=False, indent=4)
