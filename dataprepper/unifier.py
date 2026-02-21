import json
import os
import hashlib
from datetime import datetime
from config import HISTORY_DIR
from common.logger import log_status
from common.utils import format_date_str

class Unifier:
    """수집 데이터 통합 및 신규/수정 분류"""

    def __init__(self):
        self.meta_path = os.path.join(HISTORY_DIR, "GLOBAL_CONTENT_HASH.json")
        self.meta = self._load_meta()

    def _load_meta(self):
        """글로벌 지문 정보 로딩"""
        if not os.path.exists(self.meta_path): return {}
        try:
            with open(self.meta_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except: return {}

    def _save_meta(self):
        """글로벌 지문 정보 저장"""
        with open(self.meta_path, 'w', encoding='utf-8') as f:
            json.dump(self.meta, f, ensure_ascii=False, indent=4)

    def _make_fp(self, article):
        """본문/이미지 기반 지문 생성"""
        cnt, att = article.get('content', '').strip(), article.get('attachments', [])
        if cnt:
            return hashlib.md5("".join(cnt.split()).encode('utf-8')).hexdigest()
        if att:
            urls = sorted([str(x.get('attachment_url', '')) for x in att if x.get('attachment_url')])
            if urls: return hashlib.md5("".join(urls).encode('utf-8')).hexdigest()
        return None

    def _merge(self, ids1, urls1, ids2, urls2):
        """출처 정보 병합"""
        m = dict(zip(map(str, ids1), urls1))
        m.update(dict(zip(map(str, ids2), urls2)))
        s_ids = sorted([int(k) for k in m.keys()])
        return s_ids, [m[str(k)] for k in s_ids]

    def unify(self, articles):
        """데이터 통합 및 분류 수행"""
        from .deduplicate import HistoryManager
        hist_mgrs = {}
        
        groups = {}
        for a in articles:
            fp = self._make_fp(a)
            if not fp: continue
            if fp not in groups: groups[fp] = []
            groups[fp].append(a)

        inserts, updates = [], []
        changed = False

        for fp, group in groups.items():
            tmp = {}
            for a in group:
                vid, url = str(a.get('vendor_id')), a.get('original_url')
                if vid and url: tmp[vid] = url
            
            c_ids = sorted([int(v) for v in tmp.keys()])
            c_urls = [tmp[str(v)] for v in c_ids]
            rep = group[0]
            is_new_fp = fp not in self.meta
            is_upd = False

            for a in group:
                sn = a.get('site_name', 'Unknown')
                if sn not in hist_mgrs: hist_mgrs[sn] = HistoryManager(sn)
                _, up, old = hist_mgrs[sn].check(a)
                if up:
                    is_upd = True
                    rep['updated_at'] = format_date_str(datetime.now())
                    c_ids, c_urls = self._merge(c_ids, c_urls, old.get('vendor_ids', []), old.get('vendor_urls', []))
                hist_mgrs[sn].update(a)

            rep['vendor_ids'], rep['vendor_urls'] = c_ids, c_urls
            rep.pop('vendor_id', None); rep.pop('site_name', None)

            if is_upd:
                updates.append(rep)
                log_status("Unifier", f"수정 감지: {rep['title'][:15]}...", "LINK")
            elif is_new_fp:
                inserts.append(rep)
                self.meta[fp] = {'vendor_ids': c_ids, 'vendor_urls': c_urls, 'title': rep['title'], 'unique_id': rep['unique_id']}
                changed = True
            else:
                ext = self.meta[fp]
                o_ids, o_urls = ext.get('vendor_ids', []), ext.get('vendor_urls', [])
                n_ids, n_urls = self._merge(c_ids, c_urls, o_ids, o_urls)
                if len(n_ids) > len(o_ids):
                    ext['vendor_ids'], ext['vendor_urls'] = n_ids, n_urls
                    rep['vendor_ids'], rep['vendor_urls'] = n_ids, n_urls
                    inserts.append(rep); changed = True
                    log_status("Unifier", f"통합 완료: {rep['title'][:15]}...", "LINK")

        if changed: self._save_meta()
        for m in hist_mgrs.values(): m.save()
        return inserts, updates
