import asyncio
import json
import os
import sys

# 1. Windows 환경에서 Twisted AsyncioReactor 호환성을 위해 SelectorEventLoopPolicy 설정
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from twisted.internet import asyncioreactor

asyncioreactor.install()

# 2. 프로젝트 루트를 sys.path에 추가
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.append(project_root)

from scrapy.crawler import CrawlerProcess
from scrapy.utils.log import configure_logging
from scrapy.utils.project import get_project_settings

from crawlers.scrapy_app.items import validate_school_site


def run_spider():
    output_file = os.environ.get("SCRAPY_OUTPUT_FILE")
    site_info_raw = os.environ.get("SCRAPY_SITE_INFO")

    if not output_file:
        print("❌ SCRAPY_OUTPUT_FILE not set")
        sys.exit(1)

    try:
        site_info = json.loads(site_info_raw) if site_info_raw else {}
        validate_school_site(site_info)
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        print(f"❌ Invalid v10 Scrapy site metadata: {error}")
        sys.exit(1)

    site_type = site_info.get("type", "A").upper()

    # 타입에 따른 Spider 클래스 결정
    if site_type == "A":
        from crawlers.scrapy_app.spiders.type_a import TypeASpider

        spider_cls = TypeASpider
    elif site_type == "D":
        from crawlers.scrapy_app.spiders.type_d import TypeDSpider

        spider_cls = TypeDSpider
    else:
        print(f"❌ Unsupported scrapy site type: {site_type}")
        sys.exit(1)

    os.environ["SCRAPY_SETTINGS_MODULE"] = "crawlers.scrapy_app.settings"
    settings = get_project_settings()

    settings.set(
        "FEEDS",
        {output_file: {"format": "json", "encoding": "utf8", "overwrite": True}},
    )

    configure_logging(settings)
    process = CrawlerProcess(settings)
    process.crawl(spider_cls)
    process.start()


if __name__ == "__main__":
    run_spider()
