import time
import re
from datetime import datetime
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
from bs4 import BeautifulSoup
from .base import BaseCrawler


class TypeCCrawler(BaseCrawler):

    def crawl(self):
        # [리팩터링]
        self.log(f"Type C 크롤링 시작", "START")
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
            self.log(f"탭 진입: {tab['name']}")
            try:
                self.js_click(self.wait_element(By.ID, tab['id']))
                time.sleep(3)
                self._crawl_current_tab_list(tab['name'], tab['id'])
            except Exception as e:
                self.log(f"탭 이동 실패: {e}", "ERROR")

    def _crawl_current_tab_list(self, tab_name, tab_id):
        # [수정] self.limit_date 사용 (지역변수 삭제)
        page = 1

        while True:
            self.log(f"Page {page} 스캔 중...")
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

                # [수정] self.limit_date
                if date_obj < self.limit_date: continue

                cat_id = self.match_category(title_text)
                if cat_id is None: continue

                num_cell = row.select_one('th')
                num_text = num_cell.get_text(strip=True)

                try:
                    xpath = f'//table[@id="tablelist"]/tbody/tr[{i + 1}]/td[contains(@class, "text-left")]/a[1]'
                    link = self.driver.find_element(By.XPATH, xpath)
                    self.js_click(link)
                    time.sleep(1)

                    self._parse_detail_page(title_text, date_obj, cat_id, tab_id, num_text)
                    collected_count += 1

                    self.driver.back()
                    time.sleep(1)
                except Exception as e:
                    self.log(f"상세 진입 실패: {e}", "WARN")
                    self.driver.back()
                    time.sleep(2)

            if collected_count == 0:
                self.log(f"(Page {page}: 수집된 글 없음)")

            page += 1
            try:
                next_xpath = f'//ul[@class="pagination"]//a[contains(@class, "page-link") and text()="{page}"]'
                next_btn = self.wait_element(By.XPATH, next_xpath)
                self.js_click(next_btn)
                time.sleep(3)
            except:
                self.log("탭 완료.", "SUCCESS")
                break

    def _parse_detail_page(self, title_text, date_obj, cat_id, tab_id, num_text):
        try:
            self.wait_element(By.ID, "IContents_divView", timeout=5)
        except:
            pass

        soup = BeautifulSoup(self.driver.page_source, 'html.parser')

        # [수정] 여러 선택지 중 하나를 찾은 뒤 unwrap 적용
        content_div = soup.select_one('#IContents_div내용')
        if not content_div:
            content_div = soup.select_one('.board-view-cont')
        if not content_div:
            content_div = soup.select_one('#IContents_divView')

        content = ""

        if content_div:
            # 스타일 태그 벗겨내기
            for tag in content_div.find_all(['span', 'b', 'strong', 'i', 'u', 'font']):
                tag.unwrap()
            content = content_div.get_text('\n', strip=True)

        if not content:
            self.log(f"본문 없음 (Skip): {title_text[:30]}...", "WARN")
            return

        article_num = num_text
        left_area = soup.select_one('.artclViewHead .left')
        if left_area:
            for dl in left_area.select('dl'):
                dt = dl.select_one('dt')
                dd = dl.select_one('dd')
                if dt and '글번호' in dt.get_text(strip=True):
                    detail_num = dd.get_text(strip=True)
                    if detail_num:
                        article_num = detail_num
                        break

        tab_num = re.sub(r'\D', '', str(tab_id))
        unique_id = f"{self.site_code}{tab_num}{article_num}"

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