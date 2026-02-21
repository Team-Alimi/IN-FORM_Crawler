import traceback
from playwright.async_api import async_playwright
from common.utils import get_limit_date
from common.logger import log_status
import config

class PlaywrightBaseCrawler:
    """Type B, C 크롤러를 위한 공통 베이스 클래스"""

    def __init__(self, site_info):
        self.site_name = site_info['name']
        self.site_code = site_info['code']
        self.url = site_info['url']
        self.vendor_id = site_info.get('vendor_id', 0)
        
        self.playwright, self.browser, self.context, self.page = None, None, None, None
        self.collected_articles = []
        self.limit_date = get_limit_date()

    def log(self, message, level="INFO"):
        """표준 로그 출력"""
        log_status(self.site_name, message, level)

    async def _init_driver(self):
        """Playwright 브라우저 인스턴스 초기화"""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=True)
        
        # Scrapy와 동일한 User-Agent 설정 적용
        self.context = await self.browser.new_context(
            user_agent=config.FINAL_USER_AGENT
        )
        self.page = await self.context.new_page()

    async def run(self):
        """전체 수집 프로세스 실행"""
        try:
            await self._init_driver()
            await self.collect_article_list()
            self.log(f"수집 완료 (총: {len(self.collected_articles)}건)", "STOP")
            return self.site_name, self.collected_articles
        except Exception as e:
            self.log(f"수집 실패: {e}", "ERROR")
            traceback.print_exc()
            return self.site_name, []
        finally:
            await self.close()

    async def close(self):
        """브라우저 종료"""
        if self.context: await self.context.close()
        if self.browser: await self.browser.close()
        if self.playwright: await self.playwright.stop()

    async def collect_article_list(self):
        """목록 페이지 수집 (하위 클래스 구현)"""
        raise NotImplementedError
