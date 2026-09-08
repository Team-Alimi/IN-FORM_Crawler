from scrapy.exceptions import DropItem

from common.utils import process_article
from crawlers.scrapy_app.items import V10_SOURCE_FIELDS


class ValidationPipeline:
    """공통 로직을 호출하여 게시글을 정제 및 검증함"""

    def process_item(self, article, spider):
        """개별 게시글에 대한 정제 및 유효성 검사 수행"""
        raw_article = dict(article)
        if raw_article.get("source_type") != "SCHOOL" or any(
            not raw_article.get(field) for field in V10_SOURCE_FIELDS
        ):
            raise DropItem("v10 source identity validation failed")

        cleaned_article = process_article(raw_article)

        if cleaned_article is None:
            raise DropItem(f"제외 또는 검증 실패: {article.get('title', 'Unknown')}")

        return cleaned_article
