import copy
import json
import os
import tempfile

from common.redaction import sanitize_runtime_artifact
from config import HISTORY_DIR


def _write_json_atomically(path, payload):
    """Replace a JSON state file without exposing a partially-written final file."""
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    descriptor, temporary_path = tempfile.mkstemp(
        prefix=f".{os.path.basename(path)}.", suffix=".tmp", dir=directory
    )

    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            json.dump(
                sanitize_runtime_artifact(payload), file, ensure_ascii=False, indent=4
            )
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary_path, path)
    except Exception:
        if os.path.exists(temporary_path):
            os.remove(temporary_path)
        raise


class HistoryManager:
    """사이트별 수집 히스토리 관리"""

    def __init__(self, name):
        self.path = os.path.join(HISTORY_DIR, f"{name}.json")
        self.data = self._load()

    def _load(self):
        """히스토리 파일 로드 및 사전 변환"""
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                articles = json.load(f)
        except FileNotFoundError:
            return {}

        if not isinstance(articles, list):
            raise ValueError(f"히스토리 형식이 올바르지 않습니다: {self.path}")

        history = {}
        for article in articles:
            unique_id = article.get("unique_id") if isinstance(article, dict) else None
            if not isinstance(unique_id, str) or not unique_id or unique_id in history:
                raise ValueError(f"히스토리 항목 형식이 올바르지 않습니다: {self.path}")
            history[unique_id] = article

        return history

    def check(self, article):
        """기존 데이터와의 비교를 통해 신규/변경 여부 판별"""
        uid = article.get("unique_id")
        if uid not in self.data:
            return True, False, None
        old = self.data[uid]
        changed = (
            article["title"] != old.get("title")
            or article["content"] != old.get("content")
            or article.get("attachments") != old.get("attachments")
        )
        return False, changed, old

    def update(self, article):
        """메모리 내 히스토리 데이터 갱신"""
        self.data[article.get("unique_id")] = copy.deepcopy(article)

    def save(self):
        """히스토리 데이터를 파일로 저장 및 정리"""
        out = []
        for article in self.data.values():
            saved_article = copy.deepcopy(article)
            saved_article.pop("vendor_id", None)
            saved_article.pop("site_name", None)
            out.append(saved_article)
        _write_json_atomically(self.path, out)
