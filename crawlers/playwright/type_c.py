import re
import asyncio
from datetime import datetime
from .base import BaseCrawler
from common.utils import parse_date_raw, format_date_str

class TypeCCrawler(BaseCrawler):
    """다중 탭 게시판 크롤러"""

    async def parse_list(self):
        """목록 페이지 순회"""
        self.log(f"수집 시작 (기한: {self.limit.strftime('%Y-%m-%d')})", "START")
        for tid in [1, 3, 4]:
            self.log(f"Tab {tid} 진입...", "START")
            p_num, streak, prev_tits = 1, 0, []
            while True:
                sep = '&' if '?' in self.url else '?'
                url = f"{self.url}{sep}cate={tid}&page={p_num}"
                if not await self.safe_goto(url): break

                try:
                    await self.page.wait_for_selector('tbody tr', timeout=5000)
                except: break

                rows_locator = self.page.locator('tbody tr')
                if await rows_locator.count() == 0: break
                
                curr_tits = [t.strip() for t in (await self.page.locator('td.subject a').all_inner_texts()) if t.strip()]
                if curr_tits and curr_tits == prev_tits: break
                prev_tits = curr_tits

                for i in range(await rows_locator.count()):
                    try:
                        row = self.page.locator(f'tbody tr >> nth={i}')
                        sub, reg = row.locator('td.subject'), row.locator('td.regdate')
                        if await sub.count() == 0 or await reg.count() == 0: continue

                        tit_a, dt_s = sub.locator('a').first, reg.locator('span').first
                        tit, dt_txt = (await tit_a.inner_text()).strip(), (await dt_s.inner_text()).strip()
                        if not dt_txt: dt_txt = await dt_s.get_attribute('title') or ""

                        dt_obj = parse_date_raw(dt_txt)
                        if dt_obj is None: continue

                        if dt_obj < self.limit:
                            streak += 1
                            if streak >= 20: self.log(f"Tab {tid} 기한 도달.", "STOP"); break
                            continue
                        else: streak = 0

                        uid_txt = (await row.locator('._artclTdNum').inner_text()).strip() if await row.locator('._artclTdNum').count() > 0 else f"T{tid}P{p_num}R{i}"
                        
                        await tit_a.scroll_into_view_if_needed()
                        await tit_a.click(timeout=5000)
                        await self.page.wait_for_timeout(2000)
                        
                        await self.parse_detail(tit, dt_obj, tid, uid_txt)
                        
                        await self.page.go_back()
                        await self.page.wait_for_timeout(2000)
                    except Exception as e:
                        self.log(f"항목 처리 실패: {e}", "WARN")
                        await self.safe_goto(url); await self.page.wait_for_timeout(2000)
                
                if streak >= 20: break
                p_num += 1
                if p_num > 100: break

    async def parse_detail(self, title, dt_obj, tid, uid_txt):
        """상세 정보 추출"""
        loc = self.page.locator('.contents_wrap, .artclView')
        if await loc.count() == 0: return
        cnt = (await loc.first.inner_text()).strip()
        att = []
        for img in await loc.locator('img').all():
            src = await img.get_attribute('src')
            if src: att.append({'attachment_url': await self.page.evaluate(f"(src) => new URL(src, document.baseURI).href", src)})

        if not cnt and not att: return
        
        self.process_item({
            'unique_id': f"{self.code}C{tid}N{uid_txt}", 'title': title, 'content': cnt,
            'original_url': self.page.url, 'created_at': format_date_str(dt_obj),
            'updated_at': format_date_str(dt_obj), 'vendor_id': self.vendor_id, 'attachments': att
        })
