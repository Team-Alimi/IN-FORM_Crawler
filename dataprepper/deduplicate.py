import json
import os
from config import HISTORY_DIR


class Deduplicator:

    def __init__(self, site_name):
        self.site_name = site_name
        self.history_path = os.path.join(HISTORY_DIR, f"{self.site_name}.json")
        self.history_map = self._load_history()

    def _load_history(self):
        if not os.path.exists(self.history_path): return {}
        try:
            with open(self.history_path, 'r', encoding='utf-8') as f:
                data_list = json.load(f)
            return {item['unique_id']: item for item in data_list if 'unique_id' in item}
        except Exception:
            return {}

    def process_batch(self, new_articles):
        """
        데이터를 분류하고 History를 갱신하지만, 파일 저장은 하지 않고 리스트만 반환함
        """
        to_insert = []
        to_update = []

        for article in new_articles:
            uid = article.get('unique_id')

            if uid not in self.history_map:
                to_insert.append(article)
                self.history_map[uid] = article
            else:
                old_art = self.history_map[uid]
                if (article['title'] != old_art.get('title') or
                        article['content'] != old_art.get('content')):
                    to_update.append(article)
                    self.history_map[uid] = article

        # 히스토리 파일은 갱신 (다음 크롤링을 위해 필수)
        self._update_history_file()

        return to_insert, to_update

    def _update_history_file(self):
        all_data = list(self.history_map.values())
        with open(self.history_path, 'w', encoding='utf-8') as f:
            json.dump(all_data, f, ensure_ascii=False, indent=4)