import os
import sys
import asyncio

# 1. Windows 환경에서 Twisted AsyncioReactor 호환성을 위해 SelectorEventLoopPolicy 설정
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from twisted.internet import asyncioreactor
asyncioreactor.install()

# 2. 프로젝트 루트를 sys.path에 추가 (crawlers 패키지를 찾기 위함)
# 이 파일은 crawlers/ 디렉터리에 있으므로 상위 디렉터리가 루트임
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.append(project_root)

import scrapy
from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings
from scrapy.utils.log import configure_logging
from crawlers.scrapy_app.spiders.type_a import TypeASpider

def run_spider():
    # 1. 환경 변수에서 설정 읽기
    output_file = os.environ.get('SCRAPY_OUTPUT_FILE')
    
    if not output_file:
        print("❌ SCRAPY_OUTPUT_FILE not set")
        sys.exit(1)

    # 2. Scrapy 설정 로드
    os.environ['SCRAPY_SETTINGS_MODULE'] = 'crawlers.scrapy_app.settings'
    settings = get_project_settings()
    
    # 3. 결과 파일 저장 설정 (JSON)
    settings.set('FEEDS', {
        output_file: {
            'format': 'json',
            'encoding': 'utf8',
            'overwrite': True
        }
    })
    
    # 로그 설정
    configure_logging(settings)
    
    # 4. 프로세스 초기화 및 실행
    process = CrawlerProcess(settings)
    
    # Spider 클래스를 직접 지정하여 실행
    process.crawl(TypeASpider)
    
    # 블로킹 방식으로 실행 (Reactor 자동 제어)
    process.start()

if __name__ == '__main__':
    run_spider()