import sys
import os
import config

# User Agent 설정
sys.path.append(os.path.dirname(os.path.abspath('.')))

BOT_NAME = 'informBot'
USER_AGENT = config.FINAL_USER_AGENT
DEFAULT_REQUEST_HEADERS = config.COMMON_HEADERS

# 스파이더 모듈 설정
SPIDER_MODULES = ['crawlers.scrapy_app.spiders']
NEWSPIDER_MODULE = 'crawlers.scrapy_app.spiders'

# robots.txt 규칙 준수 여부
ROBOTSTXT_OBEY = False

# Scrapy가 수행할 최대 동시 요청 수 설정
CONCURRENT_REQUESTS = 1

# 동일 웹사이트에 대한 요청 지연 시간 설정
DOWNLOAD_DELAY = 2
RANDOMIZE_DOWNLOAD_DELAY = True
CONCURRENT_REQUESTS_PER_DOMAIN = 1

# 쿠키 및 콘솔 설정
COOKIES_ENABLED = True
TELNETCONSOLE_ENABLED = False

# 아이템 파이프라인 설정
ITEM_PIPELINES = {
   'crawlers.scrapy_app.pipelines.ValidationPipeline': 300,
}

REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
FEED_EXPORT_ENCODING = "utf-8"
