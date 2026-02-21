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

# Scrapy가 수행할 최대 동시 요청 수 설정 (기본값: 16)
CONCURRENT_REQUESTS = 1

# 동일 웹사이트에 대한 요청 지연 시간 설정 (기본값: 0)
# 참고: https://docs.scrapy.org/en/latest/topics/settings.html#download-delay
# autothrottle 설정 및 문서도 참고하십시오.
DOWNLOAD_DELAY = 2
RANDOMIZE_DOWNLOAD_DELAY = True
CONCURRENT_REQUESTS_PER_DOMAIN = 1

# 쿠키 비활성화 (기본적으로 활성화되어 있음)
COOKIES_ENABLED = True

# Telnet 콘솔 비활성화 (기본적으로 활성화되어 있음)
TELNETCONSOLE_ENABLED = False

# 스파이더 미들웨어 활성화 또는 비활성화
# 참고: https://docs.scrapy.org/en/latest/topics/spider-middleware.html
#SPIDER_MIDDLEWARES = {
#    'crawlers.scrapy_app.middlewares.InformCrawlerSpiderMiddleware': 543,
#}

# 다운로더 미들웨어 활성화 또는 비활성화
# 참고: https://docs.scrapy.org/en/latest/topics/downloader-middleware.html
#DOWNLOADER_MIDDLEWARES = {
#    'crawlers.scrapy_app.middlewares.InformCrawlerDownloaderMiddleware': 543,
#}

# 확장 프로그램 활성화 또는 비활성화
# 참고: https://docs.scrapy.org/en/latest/topics/extensions.html
#EXTENSIONS = {
#    'scrapy.extensions.telnet.TelnetConsole': None,
#}

# 아이템 파이프라인 설정
# 참고: https://docs.scrapy.org/en/latest/topics/item-pipeline.html
ITEM_PIPELINES = {
   'crawlers.scrapy_app.pipelines.CategoryPipeline': 300,
   'crawlers.scrapy_app.pipelines.CleanupPipeline': 400,
}

# AutoThrottle 확장 프로그램 활성화 및 설정 (기본적으로 비활성화)
# 참고: https://docs.scrapy.org/en/latest/topics/autothrottle.html
#AUTOTHROTTLE_ENABLED = True
# 최초 다운로드 지연 시간
#AUTOTHROTTLE_START_DELAY = 5
# 고지연 상황에서 설정될 최대 다운로드 지연 시간
#AUTOTHROTTLE_MAX_DELAY = 60
# 각 원격 서버에 대해 Scrapy가 병렬로 보낼 평균 요청 수
#AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0
# 수신된 모든 응답에 대해 스로틀링 통계 표시 활성화:
#AUTOTHROTTLE_DEBUG = False

# HTTP 캐싱 활성화 및 설정 (기본적으로 비활성화)
# 참고: https://docs.scrapy.org/en/latest/topics/downloader-middleware.html#httpcache-middleware-settings
#HTTPCACHE_ENABLED = True
#HTTPCACHE_EXPIRATION_SECS = 0
#HTTPCACHE_DIR = 'httpcache'
#HTTPCACHE_IGNORE_HTTP_CODES = []
#HTTPCACHE_STORAGE = 'scrapy.extensions.httpcache.FilesystemCacheStorage'

REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
FEED_EXPORT_ENCODING = "utf-8"
