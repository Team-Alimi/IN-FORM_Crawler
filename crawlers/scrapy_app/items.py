import scrapy

V10_SOURCE_FIELDS = (
    "vendor_initial",
    "source_type",
    "external_key",
    "source_url",
)


def validate_school_site(site_info):
    if not isinstance(site_info, dict):
        raise ValueError("Scrapy site metadata must be an object")

    vendor_initial = str(site_info.get("vendor_initial") or "").strip()
    source_type = str(site_info.get("source_type") or "").strip()
    source_url = str(site_info.get("url") or "").strip()

    if not vendor_initial or not source_url:
        raise ValueError("Scrapy site metadata requires vendor_initial and url")
    if source_type != "SCHOOL":
        raise ValueError("Crawler seed sources must use source_type=SCHOOL")

    return vendor_initial


def build_source_identity(vendor_initial, native_post_id, source_url):
    normalized_initial = str(vendor_initial or "").strip()
    normalized_post_id = str(native_post_id or "").strip()
    normalized_url = str(source_url or "").strip()

    if not normalized_initial or not normalized_post_id or not normalized_url:
        raise ValueError("Crawler source identity requires initial, native ID, and URL")

    return {
        "vendor_initial": normalized_initial,
        "source_type": "SCHOOL",
        "external_key": f"{normalized_initial}{normalized_post_id}",
        "source_url": normalized_url,
    }


class InformArticle(scrapy.Item):
    """스크래피 크롤링 데이터 구조"""

    unique_id = scrapy.Field()
    title = scrapy.Field()
    content = scrapy.Field()
    original_url = scrapy.Field()
    created_at = scrapy.Field()
    updated_at = scrapy.Field()
    vendor_id = scrapy.Field()  # 하위 호환용 (사용 자제)
    vendor_ids = scrapy.Field()  # 배열 구조 (신규)
    vendor_urls = scrapy.Field()  # 배열 구조 (신규)
    category_id = scrapy.Field()
    vendor_initial = scrapy.Field()
    source_type = scrapy.Field()
    external_key = scrapy.Field()
    source_url = scrapy.Field()

    # 추가 메타데이터
    site_name = scrapy.Field()
    site_code = scrapy.Field()

    # 첨부 파일 (이미지 URL 등)
    attachments = scrapy.Field()
