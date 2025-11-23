import time
from datetime import datetime
from dateutil.relativedelta import relativedelta
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup

from .base import BaseCrawler
from config import KEYWORD_CATEGORIES


class TypeACrawler(BaseCrawler):
    def crawl(self):
        self.driver.get(self.url)
        time.sleep(3)

        now = datetime.now()
        limit_date = now - relativedelta(months=2)
        limit_date = limit_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        print(f"🔍 [{self.site_name}] Type A 크롤링 시작 (Limit: {limit_date.strftime('%Y-%m-%d')})")

        page = 1
        consecutive_old_posts = 0

        while True:
            print(f"\n📄 [{self.site_name}] {page} 페이지 스캔 중...")
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            rows = soup.select('tbody tr')

            if not rows:
                print(f"⚠️ [{self.site_name}] 게시글 행을 찾지 못했습니다. 종료.")
                break

            page_processed_count = 0

            for i, row in enumerate(rows):
                date_cell = row.select_one('._artclTdRdate')
                title_cell = row.select_one('._artclTdTitle')

                if not date_cell or not title_cell:
                    continue

                date_text = date_cell.get_text(strip=True)
                title_text = title_cell.get_text(strip=True)

                # 날짜 검증
                try:
                    article_date = datetime.strptime(date_text, '%Y.%m.%d')
                    if article_date < limit_date:
                        consecutive_old_posts += 1
                        if consecutive_old_posts >= 20:
                            print(f"🛑 [{self.site_name}] 날짜 제한 도달 (연속 20회). 종료.")
                            return
                        continue
                    else:
                        consecutive_old_posts = 0
                except ValueError:
                    continue

                    # 카테고리 매칭
                matched_category_id = None
                for cat_id, keywords in KEYWORD_CATEGORIES.items():
                    if any(kw in title_text for kw in keywords):
                        matched_category_id = cat_id
                        break

                if matched_category_id is None:
                    continue

                # 상세 진입
                try:
                    xpath = f'//tbody/tr[{i + 1}]/td[contains(@class, "_artclTdTitle")]/a'
                    link = self.driver.find_element(By.XPATH, xpath)
                    self.driver.execute_script("arguments[0].scrollIntoView(true);", link)
                    self.driver.execute_script("arguments[0].click();", link)
                    time.sleep(1)

                    self._parse_detail_page(title_text, matched_category_id)
                    page_processed_count += 1

                    self.driver.back()
                    time.sleep(1)
                except Exception as e:
                    print(f"⚠️ 상세 진입 실패 ({title_text}): {e}")
                    self.driver.get(self.url)
                    time.sleep(2)

            if page_processed_count == 0:
                print(f"   (ℹ️ {page} 페이지: 수집된 글 없음)")

            page += 1
            try:
                next_btn = self.driver.find_element(By.XPATH, f'//a[contains(@onclick, "page") and text()="{page}"]')
                next_btn.click()
                time.sleep(2)
            except:
                print(f"✅ [{self.site_name}] 마지막 페이지 도달.")
                break

    def _parse_detail_page(self, list_title, category_id):
        soup = BeautifulSoup(self.driver.page_source, 'html.parser')
        content_div = soup.select_one('.artclView')
        content = content_div.get_text('\n', strip=True) if content_div else ""

        created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        updated_at = created_at

        dls = soup.select('.artclViewHead dl')
        for dl in dls:
            dt = dl.select_one('dt')
            dd = dl.select_one('dd')
            if not dt or not dd: continue

            label = dt.get_text(strip=True)
            val = dd.get_text(strip=True)

            if '작성일' in label:
                created_at = val.replace('.', '-') + " 00:00:00"
            elif '수정일' in label:
                updated_at = val.replace('.', '-') + " 00:00:00"

        self.collected_data.append({
            'title': list_title,
            'content': content,
            'original_url': self.driver.current_url,
            'created_at': created_at,
            'updated_at': updated_at,
            'vendor_id': self.vendor_id,
            'category_id': category_id
        })
        print(f"   ---> 수집 성공(Cat:{category_id}): {list_title}")