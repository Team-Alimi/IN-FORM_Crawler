import time
import re
from datetime import datetime
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup
from .base import BaseCrawler


class TypeBCrawler(BaseCrawler):

    def crawl(self):
        self.log(f"Type B 크롤링 시작 (Limit: {self.limit_date.strftime('%Y-%m-%d')})", "START")

        page = 0
        old_streak = 0

        while True:
            current_url = f"{self.url}?boardid=notice&sk=&sw=&category=&offset={page}"
            self.log(f"Page {page} 스캔 중...")
            self.driver.get(current_url)

            try:
                self.wait_elements(By.CSS_SELECTOR, 'tbody tr')
            except:
                self.log("더 이상 게시글이 없습니다.", "SUCCESS")
                break

            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            total_cnt = 0
            total_elem = soup.select_one('.total-page')
            if total_elem:
                match = re.search(r'\d+', total_elem.get_text(strip=True))
                if match:
                    total_cnt = int(match.group())

            rows = soup.select('tbody tr')
            collected_count = 0

            for i, row in enumerate(rows):
                cols = row.select('td')
                if len(cols) < 4: continue

                is_pinned = bool(row.select_one('.label') and "공지" in row.select_one('.label').get_text())
                title_text = cols[1].get_text(strip=True)
                date_text = cols[3].get_text(strip=True)

                article_num = total_cnt - page - i
                unique_id = f"{self.site_code}{article_num}"

                date_obj = self.parse_date_raw(date_text)
                if date_obj is None: continue

                if date_obj < self.limit_date:
                    if is_pinned: continue
                    old_streak += 1
                    if old_streak >= 20:
                        self.log("날짜 제한 도달. 종료.", "STOP")
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

                    self._parse_detail_page(title_text, date_obj, cat_id, unique_id)
                    collected_count += 1

                    self.driver.back()
                    time.sleep(1)
                except Exception as e:
                    self.log(f"상세 진입 실패: {e}", "WARN")
                    self.driver.get(current_url)
                    time.sleep(2)

            if collected_count == 0:
                self.log(f"(Page {page}: 수집된 글 없음)")

            page += 10
            if page > 10000:
                self.log("너무 많은 페이지 검색. 강제 종료.", "STOP")
                break

    def _parse_detail_page(self, title_text, date_obj, cat_id, unique_id):
        soup = BeautifulSoup(self.driver.page_source, 'html.parser')
        content_div = soup.select_one('.board-view-cnt')
        content = ""

        if content_div:
            # 스타일 태그 벗겨내기
            for tag in content_div.find_all(['span', 'b', 'strong', 'i', 'u', 'font']):
                tag.unwrap()
            content = content_div.get_text('\n', strip=True)

        if not content:
            self.log(f"본문 없음 (Skip): {title_text[:30]}...", "WARN")
            return

        if date_obj is None: date_obj = datetime.now()
        date_str = self.format_date_str(date_obj)

        self.collected_data.append({
            'unique_id': unique_id,
            'title': title_text,
            'content': content,
            'original_url': self.driver.current_url,
            'created_at': date_str,
            'updated_at': date_str,
            'vendor_id': self.vendor_id,
            'category_id': cat_id
        })
        self.log(f"Collected: {title_text[:30]}... (ID: {unique_id})", "COLLECT")