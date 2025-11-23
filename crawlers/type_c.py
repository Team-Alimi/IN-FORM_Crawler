import time
from datetime import datetime
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
from bs4 import BeautifulSoup
from .base import BaseCrawler


class TypeCCrawler(BaseCrawler):

    def crawl(self):
        self.driver.get(self.url)
        try:
            select_elem = self.wait_element(By.CSS_SELECTOR, "select[title='결과건수']")
            Select(select_elem).select_by_value("100")
            time.sleep(3)
        except:
            pass

        target_tabs = [
            {'id': 'tab4', 'name': '특강'},
            {'id': 'tab5', 'name': '모집'},
            {'id': 'tab6', 'name': '기타'}
        ]

        for tab in target_tabs:
            print(f"\n📂 [{self.site_name}] '{tab['name']}' 탭 진입...")
            try:
                self.js_click(self.wait_element(By.ID, tab['id']))
                time.sleep(3)
                self._crawl_current_tab_list(tab['name'])
            except:
                pass

    def _crawl_current_tab_list(self, tab_name):
        limit_date = self.get_limit_date()
        print(f"   🔍 '{tab_name}' 스캔 시작 (Limit: {limit_date.strftime('%Y-%m-%d')})")

        page = 1
        while True:
            try:
                self.wait_elements(By.CSS_SELECTOR, "#tablelist tbody tr")
            except:
                pass

            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            rows = soup.select('#tablelist tbody tr')
            if not rows: break

            collected_count = 0
            for i, row in enumerate(rows):
                title_cell = row.select_one('td.text-left')
                if not title_cell or not title_cell.select_one('a'): continue

                title_text = title_cell.select_one('a').get_text(strip=True)
                tds = row.select('td')
                if len(tds) < 3: continue

                date_text = tds[2].get_text(strip=True)
                for td in tds:
                    if len(td.text.strip()) >= 10 and '.' in td.text:
                        date_text = td.text.strip()
                        break

                date_obj = self.parse_date_raw(date_text)
                if date_obj is None: continue

                if date_obj < limit_date: continue

                cat_id = self.match_category(title_text)
                if cat_id is None: continue

                try:
                    xpath = f'//table[@id="tablelist"]/tbody/tr[{i + 1}]/td[contains(@class, "text-left")]/a[1]'
                    link = self.driver.find_element(By.XPATH, xpath)
                    self.js_click(link)
                    time.sleep(1)

                    self._parse_detail_page(title_text, date_text, cat_id)
                    collected_count += 1

                    self.driver.back()
                    time.sleep(1)
                except:
                    self.driver.back()
                    time.sleep(2)

            if collected_count == 0:
                print(f"   (ℹ️ Page {page}: 수집된 글 없음)")

            page += 1
            try:
                next_btn = self.wait_element(By.XPATH,
                                             f'//ul[@class="pagination"]//a[contains(@class, "page-link") and text()="{page}"]')
                self.js_click(next_btn)
                time.sleep(3)
            except:
                print(f"   ✅ '{tab_name}' 탭 완료.")
                break

    def _parse_detail_page(self, title_text, date_text, cat_id):
        # 1. 본문 영역 로딩 대기
        try:
            self.wait_element(By.ID, "IContents_divView", timeout=5)
        except:
            pass

        soup = BeautifulSoup(self.driver.page_source, 'html.parser')

        # 2. 본문 찾기 (ID 우선 -> Class 후순위)
        content_div = soup.select_one('#IContents_div내용')
        if not content_div:
            content_div = soup.select_one('.board-view-cont')

        if content_div:
            content = content_div.get_text('\n', strip=True)
        else:
            wrapper = soup.select_one('#IContents_divView')
            content = wrapper.get_text('\n', strip=True) if wrapper else ""

        # 3. 날짜 파싱 및 기본값(Now) 설정 로직 적용
        date_obj = self.parse_date_raw(date_text)
        if date_obj is None:
            date_obj = datetime.now()

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
        print(f"      ---> 수집: {title_text}")