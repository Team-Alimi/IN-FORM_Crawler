import re
import asyncio
from datetime import datetime
from .base import PlaywrightBaseCrawler
from common.utils import parse_date_raw, format_date_str, match_category

class TypeBCrawler(PlaywrightBaseCrawler):
    """Playwright 기반 Type B 크롤러 (동적 목록 처리)"""

    async def collect_article_list(self):
        """목록 페이지 순회 및 수집"""
        self.log(f"수집 시작 (기한: {self.limit_date.strftime('%Y-%m-%d')})", "START")

        page_offset, old_streak = 0, 0
        while True:
            current_url = f"{self.url}?boardid=notice&offset={page_offset}"
            try:
                await self.page.goto(current_url)
                await self.page.wait_for_selector('tbody tr', timeout=5000)
            except:
                self.log("페이지 로딩 종료.", "SUCCESS"); break

            # 게시글 총 개수 및 목록 추출
            total_cnt = 0
            total_elem = self.page.locator('.total-page')
            if await total_elem.count() > 0:
                match = re.search(r'\d+', await total_elem.first.inner_text())
                if match: total_cnt = int(match.group())

            rows = await self.page.locator('tbody tr').all()
            for i in range(len(rows)):
                row = self.page.locator(f'tbody tr >> nth={i}')
                cols = row.locator('td')
                if await cols.count() < 4: continue

                # 고정 공지 및 기본 정보 추출
                is_pinned = "공지" in (await row.locator('.label').first.inner_text()) if await row.locator('.label').count() > 0 else False
                title_text = (await cols.nth(1).inner_text()).strip()
                date_text = (await cols.nth(3).inner_text()).strip()

                unique_id = f"{self.site_code}{total_cnt - page_offset - i}"
                date_obj = parse_date_raw(date_text)
                if date_obj is None: continue

                # 수집 기한 및 카테고리 필터링
                if not is_pinned:
                    if date_obj < self.limit_date:
                        old_streak += 1
                        if old_streak >= 20: self.log("기한 도달로 인한 종료.", "STOP"); return
                        continue
                    else: old_streak = 0

                if match_category(title_text) is None: continue

                # 상세 페이지 진입 및 수집
                try:
                    link_locator = row.locator('td').nth(1).locator('a')
                    await link_locator.scroll_into_view_if_needed()
                    await link_locator.click(timeout=5000)
                    await self.page.wait_for_timeout(2000)

                    await self.collect_article_detail(title_text, date_obj, unique_id)

                    await self.page.go_back()
                    await self.page.wait_for_timeout(2000)
                except Exception as e:
                    self.log(f"상세 진입 실패: {e}", "WARN")
                    await self.page.goto(current_url); await self.page.wait_for_timeout(2000)

            page_offset += 10
            if page_offset > 5000: break

    async def collect_article_detail(self, title_text, date_obj, unique_id):
        """상세 페이지 내용 및 이미지 추출"""
        content_locator = self.page.locator('.board-view-cnt')
        if await content_locator.count() == 0: return

        content = (await content_locator.first.inner_text()).strip()
        attachments = []
        img_locators = await content_locator.locator('img').all()
        for img in img_locators:
            src = await img.get_attribute('src')
            if src:
                abs_url = await self.page.evaluate(f"(src) => new URL(src, document.baseURI).href", src)
                attachments.append({'attachment_url': abs_url})

        if not content and not attachments: return

        date_str = format_date_str(date_obj)
        self.collected_articles.append({
            'unique_id': unique_id,
            'title': title_text,
            'content': content,
            'original_url': self.page.url,
            'created_at': date_str,
            'updated_at': date_str,
            'vendor_id': self.vendor_id,
            'category_id': match_category(title_text),
            'attachments': attachments
        })
        self.log(f"수집 성공: {title_text[:20]}... ({len(attachments)} imgs)", "COLLECT")
