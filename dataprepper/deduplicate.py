import json
import os
import hashlib

from config import HISTORY_DIR


class Deduplicator:

    def __init__(self, site_name):
        self.site_name = site_name
        self.history_path = os.path.join(HISTORY_DIR, f"{self.site_name}.json")
        self.global_hash_path = os.path.join(HISTORY_DIR, "GLOBAL_CONTENT_HASH.json")

        self.history_map = self._load_history()
        self.global_hash_set = self._load_global_hash()

    def _load_history(self):
        """로컬 장부(사이트별 히스토리) 로딩"""
        if not os.path.exists(self.history_path): return {}
        try:
            with open(self.history_path, 'r', encoding='utf-8') as f:
                data_list = json.load(f)
            return {item['unique_id']: item for item in data_list if 'unique_id' in item}
        except Exception:
            return {}

    def _load_global_hash(self):
        """통합 지문 파일 로딩 (Set 변환)"""
        if not os.path.exists(self.global_hash_path): return set()
        try:
            with open(self.global_hash_path, 'r', encoding='utf-8') as f:
                return set(json.load(f))
        except:
            return set()

    def _update_global_hash_file(self):
        """통합 지문 파일 덮어쓰기"""
        with open(self.global_hash_path, 'w', encoding='utf-8') as f:
            json.dump(list(self.global_hash_set), f, ensure_ascii=False, indent=4)

    def _make_content_fingerprint(self, article):
        """본문 내용 기반 MD5 해시 생성 (공백 제거)"""
        content = article.get('content', '')
        if not content:
            return None

        # 공백/줄바꿈 제거하여 텍스트 알맹이만 비교
        clean_content = "".join(content.split())
        return hashlib.md5(clean_content.encode('utf-8')).hexdigest()

    def process_batch(self, new_articles):
        """중복 제거 실행 (Global -> Local 순서)"""
        to_insert = []
        to_update = []
        new_hashes_to_save = set()

        for article in new_articles:
            uid = article.get('unique_id')
            fingerprint = self._make_content_fingerprint(article)

            # Global 중복 검사 (타 사이트와 본문 일치 여부)
            if fingerprint and fingerprint in self.global_hash_set:
                # 내 장부에는 없는데 글로벌 장부에 있다면 -> 타 사이트 중복 글
                if uid not in self.history_map:
                    print(f"   ✂️ [Global 중복] 본문 일치 제거: {article['title'][:15]}...")
                    continue

            # Local 장부 검사 (신규/수정 판단)
            if uid not in self.history_map:
                # [신규]
                to_insert.append(article)
                self.history_map[uid] = article

                if fingerprint:
                    self.global_hash_set.add(fingerprint)
                    new_hashes_to_save.add(fingerprint)
            else:
                # [수정]
                old_art = self.history_map[uid]
                if (article['title'] != old_art.get('title') or
                        article['content'] != old_art.get('content')):
                    to_update.append(article)
                    self.history_map[uid] = article

        # 파일 갱신
        self._update_history_file()
        if new_hashes_to_save:
            self._update_global_hash_file()

        return to_insert, to_update

    def _update_history_file(self):
        all_data = list(self.history_map.values())
        with open(self.history_path, 'w', encoding='utf-8') as f:
            json.dump(all_data, f, ensure_ascii=False, indent=4)