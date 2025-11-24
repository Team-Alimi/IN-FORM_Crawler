import time
from datetime import datetime
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup
from .base import BaseCrawler


class TypeBCrawler(BaseCrawler):

    def crawl(self):
        limit_date = self.get_limit_date()
        print(f"🚀 [{self.site_name}] Type B 크롤링 시작 (Limit: {limit_date.strftime('%Y-%m-%d')})")

        page = 0
        old_streak = 0

        while True:
            current_url = f"{self.url}?boardid=notice&sk=&sw=&category=&offset={page}"
            print(f"📄 [{self.site_name}] Page {page} 스캔 중...")
            self.driver.get(current_url)

            # [목록 로딩]
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

                # [날짜 파싱]
                date_obj = self.parse_date_raw(date_text)
                if date_obj is None: continue

                # [날짜 비교]
                if date_obj < limit_date:
                    if is_pinned: continue
                    old_streak += 1
                    if old_streak >= 20:
                        print(f"🛑 [{self.site_name}] 날짜 제한 도달. 종료.")
                        return
                    continue
                else:
                    if not is_pinned: old_streak = 0

                    # [키워드 매칭]
                cat_id = self.match_category(title_text)
                if cat_id is None: continue

                # [상세 진입]
                try:
                    link = self.driver.find_element(By.XPATH, f'//tbody/tr[{i + 1}]/td[2]/a')
                    self.js_click(link)
                    time.sleep(1)

                    self._parse_detail_page(title_text, date_obj, cat_id)
                    collected_count += 1

                    self.driver.back()
                    time.sleep(1)
                except Exception as e:
                    print(f"⚠️ [{self.site_name}] 상세 진입 실패: {e}")
                    self.driver.get(current_url)
                    time.sleep(2)

            if collected_count == 0:
                print(f"   (ℹ️ Page {page}: 수집된 글 없음)")

            # [페이지네이션]
            page += 10
            if page > 10000:
                print("🛑 너무 많은 페이지 검색. 강제 종료.")
                break

    def _parse_detail_page(self, title_text, date_obj, cat_id):
        soup = BeautifulSoup(self.driver.page_source, 'html.parser')
        content = soup.select_one('.board-view-cnt').get_text('\n', strip=True) if soup.select_one(
            '.board-view-cnt') else ""

        if date_obj is None: date_obj = datetime.now()
        date_str = self.format_date_str(date_obj)

        self.collected_data.append({
            'title': title_text,
            'content': content,
            'original_url': self.driver.current_url,
            'created_at': date_str,
            'updated_at': date_str,
            'vendor_id': self.vendor_id,
            'category_id': cat_id
        })
        print(f"   ✨ Collected: {title_text[:30]}...")