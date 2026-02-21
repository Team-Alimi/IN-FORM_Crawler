import re
import asyncio
from datetime import datetime
from .base import PlaywrightBaseCrawler
from common.utils import parse_date_raw, format_date_str, match_category

class TypeCCrawler(PlaywrightBaseCrawler):
    """Playwright 기반 Type C 크롤러 (다중 탭 처리)"""

    async def collect_article_list(self):
        """목록 페이지 순회 및 수집"""
        self.log(f"수집 시작 (기한: {self.limit_date.strftime('%Y-%m-%d')})", "START")

        target_tabs = [1, 3, 4]
        for tab_id in target_tabs:
            self.log(f"Tab {tab_id} 진입...", "START")
            page_num, old_streak, prev_page_titles = 1, 0, []

            while True:
                separator = '&' if '?' in self.url else '?'
                current_url = f"{self.url}{separator}cate={tab_id}&page={page_num}"
                try:
                    await self.page.goto(current_url)
                    await self.page.wait_for_selector('tbody tr', timeout=5000)
                except: break

                # 1. 중복 페이지 및 빈 페이지 체크
                rows_locator = self.page.locator('tbody tr')
                if await rows_locator.count() == 0: break

                current_titles = [t.strip() for t in (await self.page.locator('td.subject a').all_inner_texts()) if t.strip()]
                if current_titles and current_titles == prev_page_titles: break
                prev_page_titles = current_titles

                # 2. 행 순회 및 수집
                for i in range(await rows_locator.count()):
                    row = self.page.locator(f'tbody tr >> nth={i}')
                    subject_td, date_td = row.locator('td.subject'), row.locator('td.regdate')
                    if await subject_td.count() == 0 or await date_td.count() == 0: continue

                    title_anchor, date_span = subject_td.locator('a').first, date_td.locator('span').first
                    title_text, date_text = (await title_anchor.inner_text()).strip(), (await date_span.inner_text()).strip()
                    if not date_text: date_text = await date_span.get_attribute('title') or ""

                    date_obj = parse_date_raw(date_text)
                    if date_obj is None: continue

                    # 기한 및 카테고리 필터링
                    if date_obj < self.limit_date:
                        old_streak += 1
                        if old_streak >= 20: self.log(f"Tab {tab_id} 기한 도달.", "STOP"); break
                        continue
                    else: old_streak = 0

                    if match_category(title_text) is None: continue
                    num_text = (await row.locator('._artclTdNum').inner_text()).strip() if await row.locator('._artclTdNum').count() > 0 else f"T{tab_id}P{page_num}R{i}"

                    # 상세 페이지 수집
                    try:
                        await title_anchor.scroll_into_view_if_needed()
                        await title_anchor.click(timeout=5000)
                        await self.page.wait_for_timeout(2000)

                        await self.collect_article_detail(title_text, date_obj, tab_id, num_text)

                        await self.page.go_back()
                        await self.page.wait_for_timeout(2000)
                    except Exception as e:
                        self.log(f"상세 진입 실패: {e}", "WARN")
                        await self.page.goto(current_url); await self.page.wait_for_timeout(2000)

                if old_streak >= 20: break
                page_num += 1
                if page_num > 100: break

    async def collect_article_detail(self, title_text, date_obj, tab_id, num_text):
        """상세 페이지 내용 및 이미지 추출"""
        content_locator = self.page.locator('.contents_wrap, .artclView')
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

        unique_id = f"{self.site_code}C{tab_id}N{num_text}"
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
