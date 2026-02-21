import json
import os
import hashlib
from config import HISTORY_DIR
from common.logger import log_status

class DataUnifier:
    """수집 데이터를 통합하고 신규/수정을 분류하는 모듈"""

    def __init__(self):
        self.global_hash_path = os.path.join(HISTORY_DIR, "GLOBAL_CONTENT_HASH.json")
        self.global_metadata = self._load_global_metadata()

    def _load_global_metadata(self):
        """글로벌 지문 정보 로딩"""
        if not os.path.exists(self.global_hash_path): return {}
        try:
            with open(self.global_hash_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except: return {}

    def _save_global_metadata(self):
        """글로벌 지문 정보 저장"""
        with open(self.global_hash_path, 'w', encoding='utf-8') as f:
            json.dump(self.global_metadata, f, ensure_ascii=False, indent=4)

    def _make_article_fingerprint(self, article):
        """본문 또는 이미지 기반 지문 생성"""
        content = article.get('content', '').strip()
        attachments = article.get('attachments', [])
        if content:
            clean_text = "".join(content.split())
            return hashlib.md5(clean_text.encode('utf-8')).hexdigest()
        elif attachments:
            urls = sorted([str(a.get('attachment_url', '')) for a in attachments if a.get('attachment_url')])
            if not urls: return None
            return hashlib.md5("".join(urls).encode('utf-8')).hexdigest()
        return None

    def _merge_vendor_info(self, ids1, urls1, ids2, urls2):
        """두 그룹의 vendor 정보를 병합하여 정렬된 배열로 반환"""
        merged = dict(zip(map(str, ids1), urls1))
        merged.update(dict(zip(map(str, ids2), urls2)))
        sorted_ids = sorted([int(k) for k in merged.keys()])
        sorted_urls = [merged[str(k)] for k in sorted_ids]
        return sorted_ids, sorted_urls

    def unify_collected_articles(self, article_list):
        """데이터 통합 및 분류 수행"""
        from .deduplicate import HistoryManager
        managers = {}
        
        fingerprint_groups = {}
        for article in article_list:
            fp = self._make_article_fingerprint(article)
            if not fp: continue
            if fp not in fingerprint_groups: fingerprint_groups[fp] = []
            fingerprint_groups[fp].append(article)

        final_inserts, final_updates = [], []
        global_changed = False

        for fp, group in fingerprint_groups.items():
            temp_map = {}
            for art in group:
                vid, url = str(art.get('vendor_id')), art.get('original_url')
                if vid and url: temp_map[vid] = url
            
            curr_ids = sorted([int(v) for v in temp_map.keys()])
            curr_urls = [temp_map[str(v)] for v in curr_ids]
            representative = group[0]
            is_globally_new = fp not in self.global_metadata
            has_local_update = False

            for art in group:
                site_name = art.get('site_name', 'Unknown')
                if site_name not in managers: managers[site_name] = HistoryManager(site_name)
                _, is_updated, old_art = managers[site_name].compare_with_history(art)
                if is_updated:
                    has_local_update = True
                    curr_ids, curr_urls = self._merge_vendor_info(curr_ids, curr_urls, old_art.get('vendor_ids', []), old_art.get('vendor_urls', []))
                managers[site_name].update_local_history(art)

            representative['vendor_ids'], representative['vendor_urls'] = curr_ids, curr_urls
            representative.pop('vendor_id', None); representative.pop('site_name', None)

            if has_local_update:
                final_updates.append(representative)
            elif is_globally_new:
                final_inserts.append(representative)
                self.global_metadata[fp] = {'vendor_ids': curr_ids, 'vendor_urls': curr_urls, 'title': representative['title'], 'unique_id': representative['unique_id']}
                global_changed = True
            else:
                existing = self.global_metadata[fp]
                old_ids, old_urls = existing.get('vendor_ids', []), existing.get('vendor_urls', [])
                new_ids, new_urls = self._merge_vendor_info(curr_ids, curr_urls, old_ids, old_urls)
                if len(new_ids) > len(old_ids):
                    existing['vendor_ids'], existing['vendor_urls'] = new_ids, new_urls
                    representative['vendor_ids'], representative['vendor_urls'] = new_ids, new_urls
                    final_inserts.append(representative)
                    global_changed = True
                    log_status("Unifier", f"내용 통합 완료: {representative['title'][:15]}... (IDs: {new_ids})", "LINK")

        if global_changed: self._save_global_metadata()
        for m in managers.values(): m.sync_history_file()
        return final_inserts, final_updates
