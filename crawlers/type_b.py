import time
from datetime import datetime
from dateutil.relativedelta import relativedelta
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup

from .base import BaseCrawler
from config import KEYWORD_CATEGORIES


class TypeBCrawler(BaseCrawler):
    def crawl(self):
        now = datetime.now()
        limit_date = now - relativedelta(months=24)
        limit_date = limit_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        print(f"🔍 [{self.site_name}] Type B 크롤링 시작 (Limit: {limit_date.strftime('%Y-%m-%d')})")

        offset = 0
        consecutive_old_posts = 0

        while True:
            current_url = f"{self.url}?boardid=notice&sk=&sw=&category=&offset={offset}"
            print(f"\n📄 [{self.site_name}] Offset {offset} 스캔 중...")
            self.driver.get(current_url)
            time.sleep(2)

            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            rows = soup.select('tbody tr')

            if not rows:
                print(f"✅ [{self.site_name}] 더 이상 게시글이 없습니다.")
                break

            page_processed_count = 0

            for i, row in enumerate(rows):
                cols = row.select('td')
                if len(cols) < 4: continue

                is_pinned = False
                label_span = row.select_one('.label')
                if label_span and "공지" in label_span.get_text():
                    is_pinned = True

                title_col = cols[1]
                date_col = cols[3]
                title_text = title_col.get_text(strip=True)
                date_text = date_col.get_text(strip=True)

                try:
                    article_date = datetime.strptime(date_text, '%Y-%m-%d')
                    if article_date < limit_date:
                        if is_pinned: continue
                        consecutive_old_posts += 1
                        if consecutive_old_posts >= 20:
                            print(f"🛑 [{self.site_name}] 날짜 제한 도달 (연속 20회). 종료.")
                            return
                        continue
                    else:
                        if not is_pinned: consecutive_old_posts = 0
                except ValueError:
                    continue

                matched_category_id = None
                for cat_id, keywords in KEYWORD_CATEGORIES.items():
                    if any(kw in title_text for kw in keywords):
                        matched_category_id = cat_id
                        break

                if matched_category_id is None:
                    continue

                try:
                    xpath = f'//tbody/tr[{i + 1}]/td[2]/a'
                    link = self.driver.find_element(By.XPATH, xpath)
                    self.driver.execute_script("arguments[0].scrollIntoView(true);", link)
                    self.driver.execute_script("arguments[0].click();", link)
                    time.sleep(1)

                    self._parse_detail_page(title_text, date_text, matched_category_id)
                    page_processed_count += 1

                    self.driver.back()
                    time.sleep(1)
                except Exception as e:
                    print(f"⚠️ 상세 진입 실패 ({title_text}): {e}")
                    self.driver.get(current_url)
                    time.sleep(2)

            if page_processed_count == 0:
                print(f"   (ℹ️ Offset {offset}: 수집된 글 없음)")

            offset += 10
            if offset > 10000:
                print("⚠️ 강제 종료.")
                break

    def _parse_detail_page(self, title, date_str, category_id):
        soup = BeautifulSoup(self.driver.page_source, 'html.parser')
        content_div = soup.select_one('.board-view-cnt')
        content = content_div.get_text('\n', strip=True) if content_div else ""

        created_at = f"{date_str} 00:00:00"
        updated_at = created_at

        self.collected_data.append({
            'title': title,
            'content': content,
            'original_url': self.driver.current_url,
            'created_at': created_at,
            'updated_at': updated_at,
            'vendor_id': self.vendor_id,
            'category_id': category_id
        })
        print(f"   ---> 수집 성공(Cat:{category_id}): {title}")