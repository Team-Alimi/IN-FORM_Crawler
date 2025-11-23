import time
from datetime import datetime
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup
from .base import BaseCrawler


class TypeBCrawler(BaseCrawler):

    def crawl(self):
        limit_date = self.get_limit_date()
        print(f"🔍 [{self.site_name}] Type B 크롤링 시작 (Limit: {limit_date.strftime('%Y-%m-%d')})")

        offset = 0
        old_streak = 0

        while True:
            current_url = f"{self.url}?boardid=notice&sk=&sw=&category=&offset={offset}"
            print(f"\n📄 [{self.site_name}] Offset {offset} 스캔 중...")
            self.driver.get(current_url)

            try:
                self.wait_elements(By.CSS_SELECTOR, 'tbody tr')
            except:
                print(f"✅ [{self.site_name}] 더 이상 게시글이 없습니다.")
                break

            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            rows = soup.select('tbody tr')
            collected_count = 0

            for i, row in enumerate(rows):
                cols = row.select('td')
                if len(cols) < 4: continue

                is_pinned = bool(row.select_one('.label') and "공지" in row.select_one('.label').get_text())
                title_text = cols[1].get_text(strip=True)
                date_text = cols[3].get_text(strip=True)

                date_obj = self.parse_date_raw(date_text)
                if date_obj is None: continue

                if date_obj < limit_date:
                    if is_pinned: continue
                    old_streak += 1
                    if old_streak >= 20:
                        print(f"🛑 [{self.site_name}] 날짜 제한 도달. 종료.")
                        return
                    continue
                else:
                    if not is_pinned: old_streak = 0

                cat_id = self.match_category(title_text)
                if cat_id is None: continue

                try:
                    link = self.driver.find_element(By.XPATH, f'//tbody/tr[{i + 1}]/td[2]/a')
                    self.js_click(link)
                    time.sleep(1)

                    self._parse_detail_page(title_text, date_text, cat_id)
                    collected_count += 1

                    self.driver.back()
                    time.sleep(1)
                except Exception as e:
                    self.driver.get(current_url)
                    time.sleep(2)

            if collected_count == 0:
                print(f"   (ℹ️ Offset {offset}: 수집된 글 없음)")

            offset += 10
            if offset > 10000: break

    def _parse_detail_page(self, title_text, date_str, cat_id):
        soup = BeautifulSoup(self.driver.page_source, 'html.parser')
        content = soup.select_one('.board-view-cnt').get_text('\n', strip=True) if soup.select_one(
            '.board-view-cnt') else ""

        dt = self.parse_date_raw(date_str)
        if dt is None: dt = datetime.now()

        date_str = self.format_date_str(dt)

        self.collected_data.append({
            'title': title_text,
            'content': content,
            'original_url': self.driver.current_url,
            'created_at': date_str,
            'updated_at': date_str,
            'vendor_id': self.vendor_id,
            'category_id': cat_id
        })
        print(f"   ---> 수집: {title_text}")