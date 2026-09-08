import asyncio
import traceback

from playwright.async_api import async_playwright

import config
from common.logger import log_status
from common.utils import get_limit_date, process_article


class BaseCrawler:
    """Playwright 기반 비동기 크롤러의 공통 기능을 정의하는 베이스 클래스"""

    def __init__(self, site):
        """사이트 정보 및 드라이버 객체를 초기화"""
        self.name, self.url = site["name"], site["url"]
        self.vendor_initial = str(site.get("vendor_initial") or "").strip()
        self.source_type = str(site.get("source_type") or "").strip()
        if not self.vendor_initial or self.source_type != "SCHOOL":
            raise ValueError("Playwright crawler site must be a SCHOOL v10 source")
        self.code = self.vendor_initial
        self.pw, self.browser, self.ctx, self.page = None, None, None, None
        self.articles = []
        self.limit = get_limit_date()

    def build_external_key(self, native_post_id):
        normalized_post_id = str(native_post_id or "").strip()
        if not normalized_post_id:
            raise ValueError("Crawler source-native identifier is required")
        return f"{self.vendor_initial}{normalized_post_id}"

    def build_source_identity(self, native_post_id, source_url):
        normalized_url = str(source_url or "").strip()
        if not normalized_url:
            raise ValueError("Crawler source URL is required")
        return {
            "vendor_initial": self.vendor_initial,
            "source_type": self.source_type,
            "external_key": self.build_external_key(native_post_id),
            "source_url": normalized_url,
        }

    def log(self, msg, lv="INFO"):
        """프로젝트 공통 로거를 통한 로그 기록"""
        log_status(self.name, msg, lv)

    async def _init_driver(self):
        """Playwright 브라우저 및 컨텍스트 초기화"""
        self.pw = await async_playwright().start()
        self.browser = await self.pw.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-setuid-sandbox",
            ],
        )
        self.ctx = await self.browser.new_context(user_agent=config.FINAL_USER_AGENT)
        self.page = await self.ctx.new_page()

    async def safe_goto(self, url, retries=3):
        """재시도 로직을 포함하여 안전하게 지정된 URL로 이동"""
        for i in range(retries):
            try:
                await self.page.goto(url, wait_until="load", timeout=30000)
                return True
            except Exception as e:
                if i == retries - 1:
                    self.log(f"이동 실패: {url} ({e})", "ERROR")
                await asyncio.sleep(2)
        return False

    async def run(self):
        """드라이버 초기화부터 파싱, 자원 해제까지의 전체 공정 실행"""
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
        """사용 중인 브라우저 및 드라이버 자원 해제"""
        try:
            if self.ctx:
                await self.ctx.close()
            if self.browser:
                await self.browser.close()
            if self.pw:
                await self.pw.stop()
        except:
            pass

    def process_item(self, article):
        """개별 게시글 데이터를 정제하고 유효한 경우 수집 목록에 추가"""
        res = process_article(article)
        if res:
            self.articles.append(res)
            self.log(f"수집: {res['title'][:20]}...", "COLLECT")
            return True
        return False

    async def parse_list(self):
        """목록 페이지 파싱 로직 (하위 클래스에서 구현)"""
        raise NotImplementedError
