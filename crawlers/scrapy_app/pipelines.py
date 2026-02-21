from scrapy.exceptions import DropItem
from common.utils import process_article

class ValidationPipeline:
    """공통 로직을 호출하여 게시글을 정제 및 검증함"""
    
    def process_item(self, item, spider):
        # 통합 정제 및 제외 키워드 검증 로직 실행
        article = process_article(dict(item))

        if article is None:
            raise DropItem(f"제외 또는 검증 실패: {item.get('title', 'Unknown')}")

        return article
