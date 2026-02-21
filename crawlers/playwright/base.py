import traceback
import asyncio
from playwright.async_api import async_playwright
from common.utils import get_limit_date, process_article, format_date_str
from common.logger import log_status
import config

class BaseCrawler:
    """Playwright 크롤러 베이스"""

    def __init__(self, site):
        self.name, self.code, self.url = site['name'], site['code'], site['url']
        self.vendor_id = site.get('vendor_id', 0)
        self.pw, self.browser, self.ctx, self.page = None, None, None, None
        self.articles = []
        self.limit = get_limit_date()

    def log(self, msg, lv="INFO"):
        log_status(self.name, msg, lv)

    async def _init_driver(self):
        """드라이버 초기화"""
        self.pw = await async_playwright().start()
        self.browser = await self.pw.chromium.launch(headless=True)
        self.ctx = await self.browser.new_context(user_agent=config.FINAL_USER_AGENT)
        self.page = await self.ctx.new_page()

    async def safe_goto(self, url, retries=3):
        """재시도를 포함한 안전한 페이지 이동"""
        for i in range(retries):
            try:
                await self.page.goto(url, wait_until="load", timeout=30000)
                return True
            except Exception as e:
                if i == retries - 1: self.log(f"이동 실패: {url} ({e})", "ERROR")
                await asyncio.sleep(2)
        return False

    async def run(self):
        """실행 및 자원 해제"""
        try:
            await self._init_driver()
            await self.parse_list()
            self.log(f"종료 (수집: {len(self.articles)}건)", "STOP")
            return self.name, self.articles
        except Exception as e:
            self.log(f"치명적 오류: {e}", "ERROR")
            traceback.print_exc()
            return self.name, []
        finally:
            await self.close()

    async def close(self):
        """자원 해제 (오타 수정됨)"""
        try:
            if self.ctx: await self.ctx.close()
            if self.browser: await self.browser.close()
            if self.pw: await self.pw.stop()
        except: pass

    def process_item(self, article):
        """게시글 정제 및 저장"""
        res = process_article(article)
        if res:
            self.articles.append(res)
            self.log(f"수집: {res['title'][:20]}...", "COLLECT")
            return True
        return False

    async def parse_list(self):
        raise NotImplementedError
