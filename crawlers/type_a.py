import time
from datetime import datetime
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup
from .base import BaseCrawler


class TypeACrawler(BaseCrawler):

    def crawl(self):
        self.driver.get(self.url)
        limit_date = self.get_limit_date()
        print(f"🔍 [{self.site_name}] Type A 크롤링 시작 (Limit: {limit_date.strftime('%Y-%m-%d')})")

        page = 1
        old_streak = 0

        while True:
            print(f"\n📄 [{self.site_name}] {page} 페이지 스캔 중...")
            try:
                self.wait_elements(By.CSS_SELECTOR, 'tbody tr')
            except:
                break

            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            rows = soup.select('tbody tr')
            collected_count = 0

            for i, row in enumerate(rows):
                date_cell = row.select_one('._artclTdRdate')
                title_cell = row.select_one('._artclTdTitle')
                if not date_cell or not title_cell: continue

                # [1] 날짜 파싱
                date_text = date_cell.get_text(strip=True)
                date_obj = self.parse_date_raw(date_text)

                if date_obj is None: continue

                # [2] 날짜 비교
                if date_obj < limit_date:
                    old_streak += 1
                    if old_streak >= 20:
                        print(f"🛑 [{self.site_name}] 날짜 제한 도달. 종료.")
                        return
                    continue
                else:
                    old_streak = 0

                title_text = title_cell.get_text(strip=True)
                cat_id = self.match_category(title_text)

                if cat_id is None: continue

                try:
                    xpath = f'//tbody/tr[{i + 1}]/td[contains(@class, "_artclTdTitle")]/a'
                    link = self.driver.find_element(By.XPATH, xpath)
                    self.js_click(link)
                    time.sleep(1)

                    # 상세 페이지 파싱
                    self._parse_detail_page(title_text, cat_id)
                    collected_count += 1

                    self.driver.back()
                    time.sleep(1)
                except Exception as e:
                    print(f"⚠️ 상세 진입 실패: {e}")
                    self.driver.get(self.url)
                    time.sleep(2)

            if collected_count == 0:
                print(f"   (ℹ️ {page} 페이지: 수집된 글 없음)")

            page += 1
            try:
                next_btn = self.wait_element(By.XPATH, f'//a[contains(@onclick, "page") and text()="{page}"]')
                self.js_click(next_btn)
                time.sleep(2)
            except:
                print(f"✅ [{self.site_name}] 마지막 페이지 도달.")
                break

    def _parse_detail_page(self, title_text, cat_id):
        # 본문 로딩 대기 (최대 5초)
        try:
            self.wait_element(By.CSS_SELECTOR, '.artclView', timeout=5)
        except:
            pass  # 본문이 없는 경우(첨부파일만 있는 경우 등)도 있으므로 패스

        soup = BeautifulSoup(self.driver.page_source, 'html.parser')

        # 본문 추출 안전장치 추가
        content_div = soup.select_one('.artclView')
        if content_div:
            content = content_div.get_text('\n', strip=True)
        else:
            content = ""  # 본문 없으면 빈 문자열

        # 기본값: 현재 시간
        created_dt = datetime.now()
        updated_dt = created_dt

        dls = soup.select('.artclViewHead dl')
        for dl in dls:
            dt_elem = dl.select_one('dt')
            dd_elem = dl.select_one('dd')

            # dt나 dd가 하나라도 없으면 건너뛰기 (방어 코드)
            if not dt_elem or not dd_elem:
                continue

            label = dt_elem.get_text(strip=True)
            val = dd_elem.get_text(strip=True)

            dt_obj = self.parse_date_raw(val)
            if dt_obj:
                if '작성일' in label:
                    created_dt = dt_obj
                elif '수정일' in label:
                    updated_dt = dt_obj

        created_str = self.format_date_str(created_dt)
        updated_str = self.format_date_str(updated_dt)

        self.collected_data.append({
            'title': title_text,
            'content': content,
            'original_url': self.driver.current_url,
            'created_at': created_str,
            'updated_at': updated_str,
            'vendor_id': self.vendor_id,
            'category_id': cat_id
        })
        print(f"   ---> 수집: {title_text}")