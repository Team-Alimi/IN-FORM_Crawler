import time
from datetime import datetime
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup
from .base import BaseCrawler


class TypeACrawler(BaseCrawler):

    def crawl(self):
        limit_date = self.get_limit_date()
        print(f"🚀 [{self.site_name}] Type A 크롤링 시작 (Limit: {limit_date.strftime('%Y-%m-%d')})")

        self.driver.get(self.url)
        page = 1
        old_streak = 0

        while True:
            print(f"📄 [{self.site_name}] Page {page} 스캔 중...")

            # [목록 로딩]
            try:
                self.wait_elements(By.CSS_SELECTOR, 'tbody tr')
            except:
                print(f"✅ [{self.site_name}] 게시글 로딩 실패 또는 끝.")
                break

            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            rows = soup.select('tbody tr')
            collected_count = 0

            for i, row in enumerate(rows):
                # [데이터 추출]
                date_cell = row.select_one('._artclTdRdate')
                title_cell = row.select_one('._artclTdTitle')
                if not date_cell or not title_cell: continue

                date_text = date_cell.get_text(strip=True)
                title_text = title_cell.get_text(strip=True)

                # [날짜 검증]
                date_obj = self.parse_date_raw(date_text)
                if date_obj is None: continue

                if date_obj < limit_date:
                    old_streak += 1
                    if old_streak >= 20:
                        print(f"🛑 [{self.site_name}] 날짜 제한 도달. 종료.")
                        return
                    continue
                else:
                    old_streak = 0

                # [키워드 매칭]
                cat_id = self.match_category(title_text)
                if cat_id is None: continue

                # [상세 진입]
                try:
                    xpath = f'//tbody/tr[{i + 1}]/td[contains(@class, "_artclTdTitle")]/a'
                    link = self.driver.find_element(By.XPATH, xpath)
                    self.js_click(link)
                    time.sleep(1)

                    self._parse_detail_page(title_text, cat_id)
                    collected_count += 1

                    self.driver.back()
                    time.sleep(1)
                except Exception as e:
                    print(f"⚠️ [{self.site_name}] 상세 진입 실패: {e}")
                    self.driver.get(self.url)
                    time.sleep(2)

            if collected_count == 0:
                print(f"   (ℹ️ Page {page}: 수집된 글 없음)")

            # [페이지네이션]
            page += 1
            try:
                next_btn = self.wait_element(By.XPATH, f'//a[contains(@onclick, "page") and text()="{page}"]')
                self.js_click(next_btn)
                time.sleep(2)
            except:
                print(f"✅ [{self.site_name}] 마지막 페이지 도달.")
                break

    def _parse_detail_page(self, title_text, cat_id):
        # [본문 대기]
        try:
            self.wait_element(By.CSS_SELECTOR, '.artclView', timeout=5)
        except:
            pass

        soup = BeautifulSoup(self.driver.page_source, 'html.parser')
        content_div = soup.select_one('.artclView')
        content = content_div.get_text('\n', strip=True) if content_div else ""

        # [상세 날짜 파싱]
        # 기본값: 현재 시간
        created_dt = datetime.now()
        updated_dt = created_dt

        # 상세 페이지 헤더에서 정확한 작성일/수정일 추출 시도
        dls = soup.select('.artclViewHead dl')
        for dl in dls:
            dt_elem = dl.select_one('dt')
            dd_elem = dl.select_one('dd')

            if not dt_elem or not dd_elem: continue

            label = dt_elem.get_text(strip=True)
            val = dd_elem.get_text(strip=True)

            date_obj = self.parse_date_raw(val)
            if date_obj:
                if '작성일' in label:
                    created_dt = date_obj
                elif '수정일' in label:
                    updated_dt = date_obj

        # DB 저장용 문자열 변환
        date_str_created = self.format_date_str(created_dt)
        date_str_updated = self.format_date_str(updated_dt)

        self.collected_data.append({
            'title': title_text,
            'content': content,
            'original_url': self.driver.current_url,
            'created_at': date_str_created,
            'updated_at': date_str_updated,
            'vendor_id': self.vendor_id,
            'category_id': cat_id
        })
        print(f"   ✨ Collected: {title_text[:30]}...")