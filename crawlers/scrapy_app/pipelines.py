from scrapy.exceptions import DropItem
from common.utils import process_article

class ValidationPipeline:
    """공통 로직을 호출하여 게시글을 정제 및 검증함"""
    
    def process_item(self, article, spider):
        """개별 게시글에 대한 정제 및 유효성 검사 수행"""
        cleaned_article = process_article(dict(article))

        if cleaned_article is None:
            raise DropItem(f"제외 또는 검증 실패: {article.get('title', 'Unknown')}")

        return cleaned_article
