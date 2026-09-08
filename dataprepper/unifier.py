import copy
import hashlib
import json
import os
from datetime import datetime

from common.logger import log_status
from common.utils import format_date_str
from config import HISTORY_DIR
from dataprepper.deduplicate import _write_json_atomically


class Unifier:
    """수집 데이터 통합 및 신규/수정 분류"""

    def __init__(self):
        self.meta_path = os.path.join(HISTORY_DIR, "GLOBAL_CONTENT_HASH.json")
        self.meta = self._load_meta()

    def _load_meta(self):
        """글로벌 지문 정보 로딩"""
        try:
            with open(self.meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
        except FileNotFoundError:
            return {}

        if not isinstance(meta, dict) or any(
            not isinstance(fingerprint, str) or not isinstance(entry, dict)
            for fingerprint, entry in meta.items()
        ):
            raise ValueError(f"지문 메타 형식이 올바르지 않습니다: {self.meta_path}")

        return meta

    def _save_meta(self):
        """글로벌 지문 정보 저장"""
        _write_json_atomically(self.meta_path, self.meta)

    def _make_fp(self, article):
        """본문/이미지 기반 지문 생성"""
        cnt, att = article.get("content", "").strip(), article.get("attachments", [])
        if cnt:
            return hashlib.md5("".join(cnt.split()).encode("utf-8")).hexdigest()
        if att:
            urls = sorted(
                [
                    str(x.get("attachment_url", ""))
                    for x in att
                    if x.get("attachment_url")
                ]
            )
            if urls:
                return hashlib.md5("".join(urls).encode("utf-8")).hexdigest()
        return None

    @staticmethod
    def _source_identity(article):
        vendor_initial = str(article.get("vendor_initial") or "").strip()
        external_key = str(article.get("external_key") or "").strip()
        source_type = article.get("source_type")

        if source_type != "SCHOOL" or not vendor_initial or not external_key:
            raise ValueError("v10 source identity is required before unification")

        return vendor_initial, external_key

    def _merge(self, ids1, urls1, ids2, urls2):
        """다중 출처 정보를 병합하여 동일 게시글에 대한 접근 경로의 가용성을 극대화함"""
        m = dict(zip(map(str, ids1), urls1))
        m.update(dict(zip(map(str, ids2), urls2)))
        s_ids = sorted([int(k) for k in m])
        return s_ids, [m[str(k)] for k in s_ids]

    def unify(self, articles):
        """지속형 다계층 그룹화를 통해 중복을 제거하고 마스터 레코드를 선정함"""
        from .deduplicate import HistoryManager
        from .similarity_engine import SimilarityEngine
        from .text_cleaner import Cleaner

        engine = SimilarityEngine()
        cleaner = Cleaner()
        hist_mgrs = {}

        prepared_articles = [copy.deepcopy(article) for article in articles]

        # === PHASE 1: 데이터 전처리 ===
        for a in prepared_articles:
            self._source_identity(a)
            a["norm_title"] = cleaner.normalize_for_similarity(a["title"])
            a["content_raw"] = cleaner.clean_html_to_text(a.get("content", ""))

        ## === PHASE 2: Fuzzy Matching & Jaccard Matching ===
        from .similarity_engine import JACCARD_THRESHOLD

        groups = []
        for a in prepared_articles:
            found_group = None

            for group in groups:
                rep = group[0]
                if self._source_identity(a) != self._source_identity(rep):
                    continue

                # [1] Fuzzy Title Matching
                if engine.fuzzy_match(a["norm_title"], rep["norm_title"]):
                    found_group = group
                    break

                # [2] Jaccard Matching
                sim = engine.get_jaccard_similarity(a, rep)
                if sim >= JACCARD_THRESHOLD:
                    found_group = group
                    break

            if found_group:
                found_group.append(a)
            else:
                groups.append([a])

        inserts, updates = [], []

        # === PHASE 3: 그룹별 통합 및 상태 판별 ===
        for group in groups:
            # 게시글 수정 여부 판별
            is_upd = False
            is_new_source = False
            for a in group:
                sn = a.get("site_name", "Unknown")
                if sn not in hist_mgrs:
                    hist_mgrs[sn] = HistoryManager(sn)
                is_new, up, _ = hist_mgrs[sn].check(a)
                if is_new:
                    is_new_source = True
                if up:
                    is_upd = True
                    a["is_updated_delta"] = True

            # 대표 데이터(Master) 선정
            # 우선순위: 수정 여부 > 최신 날짜 > 정보량
            master = sorted(
                group,
                key=lambda x: (
                    x.get("is_updated_delta", False),
                    x.get("created_at", ""),
                    len(x.get("content_raw", "") or ""),
                    len(x.get("attachments", []) or ""),
                ),
                reverse=True,
            )[0]

            master.pop("is_updated_delta", None)

            if is_upd:
                master["updated_at"] = format_date_str(datetime.now())
                updates.append(master)
                log_status("Unifier", f"수정 감지: {master['title'][:15]}...", "LINK")
            elif is_new_source:
                inserts.append(master)
                log_status(
                    "Unifier", f"신규 수집: {master['title'][:15]}...", "COLLECT"
                )

        return inserts, updates

    def commit(self, inserts, updates):
        """AI 분류가 완료된 최종 데이터를 히스토리에 기록하고 파일로 저장함"""
        if not inserts and not updates:
            return

        from .deduplicate import HistoryManager

        hist_mgrs = {}
        all_articles = inserts + updates

        for article in all_articles:
            a = copy.deepcopy(article)
            vendor_initial, external_key = self._source_identity(a)
            self.meta[f"{vendor_initial}:{external_key}"] = {
                "source_url": a.get("source_url"),
                "title": a.get("title"),
                "unique_id": a.get("unique_id"),
            }

            # 사이트별 상세 히스토리 업데이트
            site_name = a.pop("site_name", "Global")
            if site_name not in hist_mgrs:
                hist_mgrs[site_name] = HistoryManager(site_name)

            hist_mgrs[site_name].update(a)

        # 최종 파일 저장
        self._save_meta()
        for m in hist_mgrs.values():
            m.save()
        log_status(
            "Unifier", f"히스토리 확정 완료 ({len(all_articles)}건 기록)", "SAVE"
        )
