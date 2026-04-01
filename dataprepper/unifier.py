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
        """다중 출처 정보를 병합하여 동일 게시글에 대한 접근 경로의 가용성을 극대화함"""
        m = dict(zip(map(str, ids1), urls1))
        m.update(dict(zip(map(str, ids2), urls2)))
        s_ids = sorted([int(k) for k in m.keys()])
        return s_ids, [m[str(k)] for k in s_ids]

    def unify(self, articles):
        """지속형 다계층 그룹화를 통해 중복을 제거하고 마스터 레코드를 선정함"""
        from .similarity_engine import SimilarityEngine
        from .text_cleaner import Cleaner
        from .deduplicate import HistoryManager
        
        engine = SimilarityEngine()
        cleaner = Cleaner()
        hist_mgrs = {}

        # === PHASE 1: 데이터 전처리 ===
        for a in articles:
            a['norm_title'] = cleaner.normalize_for_similarity(a['title'])
            a['content_raw'] = cleaner.clean_html_to_text(a.get('content', ''))

        ## === PHASE 2: Fuzzy Matching & Jaccard Matching ===
        from .similarity_engine import JACCARD_THRESHOLD, GREY_ZONE_THRESHOLD

        groups = []
        for a in articles:
            found_group = None
            max_sim = 0.0

            for group in groups:
                rep = group[0]
                # [1] Fuzzy Title Matching
                if engine.fuzzy_match(a['norm_title'], rep['norm_title']):
                    found_group = group; break
                
                # [2] Jaccard Matching
                sim = engine.get_jaccard_similarity(a, rep)
                if sim >= JACCARD_THRESHOLD:
                    found_group = group; break
                
                # [3] Grey Zone 식별을 위해 최대 유사도 기록
                if sim > max_sim:
                    max_sim = sim
            
            if found_group:
                found_group.append(a)
            else:
                # 어느 그룹에도 속하지 않았으나, Grey Zone 범위에 있다면 마킹
                if max_sim >= GREY_ZONE_THRESHOLD:
                    a['admin_status'] = 'SUSPECTED_DUPLICATE'
                groups.append([a])

        inserts, updates = [], []

        # === PHASE 3: 그룹별 통합 및 상태 판별 ===
        for group in groups:
            # 게시글 수정 여부 판별
            is_upd = False
            for a in group:
                sn = a.get('site_name', 'Unknown')
                if sn not in hist_mgrs: hist_mgrs[sn] = HistoryManager(sn)
                _, up, old = hist_mgrs[sn].check(a)
                if up:
                    is_upd = True; a['is_updated_delta'] = True
                    # 수정 감지 시 기존 출처 정보 병합을 위해 저장
                    a['old_vendor_ids'], a['old_vendor_urls'] = old.get('vendor_ids', []), old.get('vendor_urls', [])
            
            # 대표 데이터(Master) 선정
            # 우선순위: 수정 여부 > 최신 날짜 > 정보량
            master = sorted(group, key=lambda x: (
                x.get('is_updated_delta', False),
                x.get('created_at', ''),
                len(x.get('content_raw', '') or ''),
                len(x.get('attachments', []) or '')
            ), reverse=True)[0]

            # 출처 통합
            tmp_sources = {}
            for a in group:
                # 개별 출처 정보
                for i, vid in enumerate(a.get('vendor_ids', [])):
                    tmp_sources[str(vid)] = a.get('vendor_urls', [])[i]
                # 수정 데이터의 경우 기존 출처 정보도 통합
                if a.get('is_updated_delta'):
                    for i, vid in enumerate(a.get('old_vendor_ids', [])):
                        tmp_sources[str(vid)] = a.get('old_vendor_urls', [])[i]
            
            c_ids = sorted([int(v) for v in tmp_sources.keys() if v.isdigit()])
            c_urls = [tmp_sources[str(v)] for v in c_ids]
            
            master['vendor_ids'], master['vendor_urls'] = c_ids, c_urls
            master.pop('is_updated_delta', None); master.pop('old_vendor_ids', None); master.pop('old_vendor_urls', None)

            # 글로벌 지문 히스토리 체크 및 최종 분류
            fp = self._make_fp(master)
            is_new_fp = fp not in self.meta

            if is_upd:
                master['updated_at'] = format_date_str(datetime.now())
                updates.append(master)
                log_status("Unifier", f"수정 감지: {master['title'][:15]}...", "LINK")
            elif is_new_fp:
                inserts.append(master)
                log_status("Unifier", f"신규 수집: {master['title'][:15]}...", "COLLECT")
            else:
                # 기존 FP가 존재하나 출처 정보가 확장된 경우 Insert 처리 (Deduplicate에서 신규 취급)
                if len(c_ids) > len(self.meta[fp].get('vendor_ids', [])):
                    inserts.append(master)
                    log_status("Unifier", f"통합 완료: {master['title'][:15]}...", "LINK")

        return inserts, updates

    def commit(self, inserts, updates):
        """AI 분류가 완료된 최종 데이터를 히스토리에 기록하고 파일로 저장함"""
        if not inserts and not updates: return
        
        from .deduplicate import HistoryManager
        hist_mgrs = {}
        all_articles = inserts + updates
        
        for a in all_articles:
            # 지문 메타데이터 업데이트
            fp = self._make_fp(a)
            if fp:
                self.meta[fp] = {
                    'vendor_ids': a.get('vendor_ids', []), 
                    'vendor_urls': a.get('vendor_urls', []), 
                    'title': a.get('title'), 
                    'unique_id': a.get('unique_id')
                }
            
            # 사이트별 상세 히스토리 업데이트
            site_name = a.pop('site_name', 'Global')
            if site_name not in hist_mgrs:
                hist_mgrs[site_name] = HistoryManager(site_name)
            
            hist_mgrs[site_name].update(a)

        # 최종 파일 저장
        self._save_meta()
        for m in hist_mgrs.values():
            m.save()
        log_status("Unifier", f"히스토리 확정 완료 ({len(all_articles)}건 기록)", "SAVE")
