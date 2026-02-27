import scrapy

class InformArticle(scrapy.Item):
    """스크래피 크롤링 데이터 구조"""
    unique_id = scrapy.Field()
    title = scrapy.Field()
    content = scrapy.Field()
    original_url = scrapy.Field()
    created_at = scrapy.Field()
    updated_at = scrapy.Field()
    vendor_id = scrapy.Field()
    category_id = scrapy.Field()
    
    # 추가 메타데이터
    site_name = scrapy.Field()
    site_code = scrapy.Field()
    
    # 첨부 파일 (이미지 URL 등)
    attachments = scrapy.Field()
