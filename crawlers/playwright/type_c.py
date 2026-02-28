from .base import BaseCrawler
from common.utils import parse_date_raw, format_date_str

class TypeCCrawler(BaseCrawler):
    """카테고리 탭이 분리된 게시판(Type C)을 위한 Playwright 크롤러 구현체"""

    async def parse_list(self):
        """지정된 카테고리 탭들을 순회하며 각 목록 페이지를 파싱"""
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
        """상세 페이지에서 본문 및 첨부파일을 추출하고 부모 클래스의 정제 로직 호출"""
        loc = self.page.locator('.contents_wrap, .artclView')
        if await loc.count() == 0: return

        # DOM 조작 전 이미지 첨부파일 먼저 추출
        att = []
        for img in await loc.locator('img').all():
            src = await img.get_attribute('src')
            if src: att.append({'attachment_url': await self.page.evaluate(f"(src) => new URL(src, document.baseURI).href", src)})

        # 표(Table)를 마크다운 형식으로 치환 (개행 방지 및 정제)
        await self.page.evaluate('''() => {
            const tables = document.querySelectorAll('.board-view-cnt table, .artclView table, .contents_wrap table');
            tables.forEach(table => {
                let md = '\\n\\n';
                table.querySelectorAll('tr').forEach((row, i) => {
                    let cols = Array.from(row.querySelectorAll('th, td')).map(c => c.innerText.trim().replace(/\\n/g, ' '));
                    if (cols.length === 0) return;
                    md += '| ' + cols.join(' | ') + ' |\\n';
                    if (i === 0) md += '|' + cols.map(() => '---').join('|') + '|\\n';
                });
                const textNode = document.createTextNode(md + '\\n');
                table.parentNode.replaceChild(textNode, table);
            });
        }''')

        cnt = (await loc.first.inner_text()).strip()

        if not cnt and not att: return
        
        self.process_item({
            'unique_id': f"{self.code}C{tid}N{uid_txt}", 'title': title, 'content': cnt,
            'original_url': self.page.url, 'created_at': format_date_str(dt_obj),
            'updated_at': format_date_str(dt_obj), 'vendor_id': self.vendor_id, 'attachments': att
        })
