import scrapy

class InformItem(scrapy.Item):
    unique_id = scrapy.Field()
    title = scrapy.Field()
    content = scrapy.Field()
    original_url = scrapy.Field()
    created_at = scrapy.Field()
    updated_at = scrapy.Field()
    vendor_id = scrapy.Field()
    category_id = scrapy.Field()
