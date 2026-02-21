import re
import asyncio
from datetime import datetime
from .base import BaseCrawler
from common.utils import parse_date_raw, format_date_str

class TypeBCrawler(BaseCrawler):
    """동적 목록형 크롤러"""

    async def parse_list(self):
        self.log(f"수집 시작 (기한: {self.limit.strftime('%Y-%m-%d')})", "START")
        off, streak = 0, 0
        while True:
            url = f"{self.url}?boardid=notice&offset={off}"
            # 안전한 페이지 이동
            if not await self.safe_goto(url): break
            
            try:
                await self.page.wait_for_selector('tbody tr', timeout=5000)
            except:
                break

            tot = 0
            t_elem = self.page.locator('.total-page')
            if await t_elem.count() > 0:
                m = re.search(r'\d+', await t_elem.first.inner_text())
                if m: tot = int(m.group())

            rows = await self.page.locator('tbody tr').all()
            for i in range(len(rows)):
                try:
                    row = self.page.locator(f'tbody tr >> nth={i}')
                    cols = row.locator('td')
                    if await cols.count() < 4: continue

                    pinned = "공지" in (await row.locator('.label').first.inner_text()) if await row.locator('.label').count() > 0 else False
                    tit, dt_txt = (await cols.nth(1).inner_text()).strip(), (await cols.nth(3).inner_text()).strip()
                    uid = f"{self.code}{tot - off - i}"
                    dt_obj = parse_date_raw(dt_txt)
                    if dt_obj is None: continue

                    if dt_obj < self.limit:
                        if not pinned:
                            streak += 1
                            if streak >= 20: self.log("기한 종료.", "STOP"); return
                        continue
                    else:
                        if not pinned: streak = 0

                    lnk = row.locator('td').nth(1).locator('a')
                    await lnk.scroll_into_view_if_needed()
                    await lnk.click(timeout=5000)
                    await self.page.wait_for_timeout(2000)
                    
                    await self.parse_detail(tit, dt_obj, uid)
                    
                    await self.page.go_back()
                    await self.page.wait_for_timeout(2000)
                except Exception as e:
                    self.log(f"항목 처리 실패: {e}", "WARN")
                    # 실패 시 현재 목록 페이지로 복구 시도
                    await self.safe_goto(url)
                    await self.page.wait_for_timeout(2000)

            off += 10
            if off > 5000: break

    async def parse_detail(self, title, dt_obj, uid):
        """상세 정보 추출"""
        loc = self.page.locator('.board-view-cnt')
        if await loc.count() == 0: return
        cnt = (await loc.first.inner_text()).strip()
        att = []
        for img in await loc.locator('img').all():
            src = await img.get_attribute('src')
            if src: att.append({'attachment_url': await self.page.evaluate(f"(src) => new URL(src, document.baseURI).href", src)})

        self.process_item({
            'unique_id': uid, 'title': title, 'content': cnt,
            'original_url': self.page.url, 'created_at': format_date_str(dt_obj),
            'updated_at': format_date_str(dt_obj), 'vendor_id': self.vendor_id, 'attachments': att
        })
