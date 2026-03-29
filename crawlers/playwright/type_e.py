import asyncio
from .base import BaseCrawler
from common.utils import parse_date_raw, format_date_str

class TypeECrawler(BaseCrawler):
    """인하대 본교 공지사항(Type E)을 위한 Playwright 크롤러 구현체"""

    async def _init_driver(self):
        """부모 클래스의 드라이버 초기화를 확장하여 리소스 차단 로직 추가"""
        await super()._init_driver()
        await self.page.route("**/*", lambda route: route.abort() 
            if route.request.resource_type in ["image", "font", "media"] 
            else route.continue_())
        self.log("리소스 차단 활성화 (image, font, media)", "PHASE")

    async def parse_list(self):
        """목록 페이지를 순회하며 수집 대상을 먼저 추출한 뒤 상세 방문 (안정성 강화)"""
        self.log(f"수집 시작 (기한: {self.limit.strftime('%Y-%m-%d')})", "START")
        
        page_num = 1
        streak = 0
        
        while True:
            sep = "&" if "?" in self.url else "?"
            list_url = f"{self.url}{sep}page={page_num}"
            
            if not await self.safe_goto(list_url):
                break
            
            # 목록 로딩 대기
            try:
                await self.page.wait_for_selector('tbody tr', timeout=10000)
            except:
                self.log(f"목록 로딩 실패 (Page {page_num})", "WARN")
                break
            
            rows_loc = self.page.locator('tbody tr')
            rows_count = await rows_loc.count()
            if rows_count == 0:
                break
                
            items_to_visit = []
            found_valid_in_page = False

            for i in range(rows_count):
                try:
                    row = rows_loc.nth(i)
                    num_loc = row.locator('._artclTdNum').first
                    
                    # 데이터 로딩 대기
                    await num_loc.wait_for(state="visible", timeout=5000)
                    
                    art_num = (await num_loc.inner_text()).strip()
                    is_pinned = not art_num.isdigit()
                    
                    title_elem = row.locator('._artclTdTitle').first
                    title = (await title_elem.inner_text()).strip()
                    dt_txt = (await row.locator('._artclTdRdate').first.inner_text()).strip()
                    
                    dt_obj = parse_date_raw(dt_txt)
                    if not dt_obj or dt_obj < self.limit:
                        if not is_pinned:
                            streak += 1
                            if streak >= 20:
                                break
                        continue
                    else:
                        if not is_pinned:
                            streak = 0
                            found_valid_in_page = True

                    link_elem = title_elem.locator('a').first
                    href = await link_elem.get_attribute('href')
                    if href:
                        abs_url = await self.page.evaluate(f"(src) => new URL(src, document.baseURI).href", href)
                        items_to_visit.append({
                            'url': abs_url,
                            'title': title,
                            'dt_obj': dt_obj,
                            'art_num': art_num
                        })
                except Exception as e:
                    continue

            if streak >= 20:
                self.log("20건 연속 기한 초과로 수집 종료", "STOP")
                return

            for item in items_to_visit:
                try:
                    if await self.safe_goto(item['url']):
                        # 상세 페이지 로딩 대기
                        await self.page.wait_for_selector('.artclView', timeout=15000)
                        await self.parse_detail(item['title'], item['dt_obj'], item['art_num'])
                        await asyncio.sleep(0.5)
                except Exception as e:
                    self.log(f"상세 페이지 접근 오류 ({item['title'][:10]}): {e}", "WARN")

            if not found_valid_in_page and page_num > 1:
                break
            
            page_num += 1
            if page_num > 100:
                break

    async def parse_detail(self, title, dt_obj, art_num):
        """상세 페이지에서 본문 및 이미지 추출"""
        try:
            view = self.page.locator('.artclView').first
            if await view.count() == 0:
                return

            # 원본 HTML 추출
            raw_html = await view.inner_html()
            images = await view.locator('img').all()
            attachments = []
            for img in images:
                src = await img.get_attribute('src')
                if src:
                    # 상대 경로를 절대 경로로 변환
                    abs_url = await self.page.evaluate(f"(src) => new URL(src, document.baseURI).href", src)
                    attachments.append({'attachment_url': abs_url})
            
            uid = f"{self.code}{art_num}"
            
            self.process_item({
                'unique_id': uid,
                'title': title,
                'content': raw_html,
                'original_url': self.page.url,
                'created_at': format_date_str(dt_obj),
                'updated_at': format_date_str(dt_obj),
                'vendor_ids': [self.vendor_id],
                'vendor_urls': [self.page.url],
                'attachments': attachments
            })
            
        except Exception as e:
            self.log(f"상세 페이지 파싱 오류: {e}", "WARN")
