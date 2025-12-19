import time
from datetime import datetime
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup
from .base import BaseCrawler


class TypeACrawler(BaseCrawler):

    def crawl(self):
        self.log(f"Type A 크롤링 시작 (Limit: {self.limit_date.strftime('%Y-%m-%d')})", "START")

        self.driver.get(self.url)
        page = 1
        old_streak = 0

        while True:
            self.log(f"Page {page} 스캔 중...")

            try:
                self.wait_elements(By.CSS_SELECTOR, 'tbody tr')
            except:
                self.log("게시글 로딩 실패 또는 끝.", "SUCCESS")
                break

            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            rows = soup.select('tbody tr')
            collected_count = 0

            for i, row in enumerate(rows):
                date_cell = row.select_one('._artclTdRdate')
                title_cell = row.select_one('._artclTdTitle')
                if not date_cell or not title_cell: continue

                num_cell = row.select_one('._artclTdNum')
                num_text = num_cell.get_text(strip=True)

                date_text = date_cell.get_text(strip=True)
                title_text = title_cell.get_text(strip=True)

                date_obj = self.parse_date_raw(date_text)
                if date_obj is None: continue

                if date_obj < self.limit_date:
                    old_streak += 1
                    if old_streak >= 20:
                        self.log("날짜 제한 도달. 종료.", "STOP")
                        return
                    continue
                else:
                    old_streak = 0

                cat_id = self.match_category(title_text)
                if cat_id is None: continue

                try:
                    xpath = f'//tbody/tr[{i + 1}]/td[contains(@class, "_artclTdTitle")]/a'
                    link = self.driver.find_element(By.XPATH, xpath)
                    self.js_click(link)
                    time.sleep(1)

                    self._parse_detail_page(title_text, cat_id, num_text)
                    collected_count += 1

                    self.driver.back()
                    time.sleep(1)
                except Exception as e:
                    self.log(f"상세 진입 실패: {e}", "WARN")
                    self.driver.get(self.url)
                    time.sleep(2)

            if collected_count == 0:
                self.log(f"(Page {page}: 수집된 글 없음)")

            page += 1
            try:
                next_btn = self.wait_element(By.XPATH, f'//a[contains(@onclick, "page") and text()="{page}"]')
                self.js_click(next_btn)
                time.sleep(2)
            except:
                self.log("마지막 페이지 도달.", "SUCCESS")
                break

    def _parse_detail_page(self, title_text, cat_id, num_text):
        try:
            self.wait_element(By.CSS_SELECTOR, '.artclView', timeout=5)
        except:
            pass

        soup = BeautifulSoup(self.driver.page_source, 'html.parser')
        content_div = soup.select_one('.artclView')
        content = ""
        if content_div:
            # <br> 태그를 실제 줄바꿈 문자로 변경
            for br in content_div.find_all('br'):
                br.replace_with('\n')

            # 문단(p, div, li)이 끝날 때 줄바꿈 문자 추가 (문단 구분용)
            for block in content_div.find_all(['p', 'div', 'li', 'tr']):
                block.append('\n')

            # 문장을 끊어먹는 인라인 태그들 껍질 벗기기 (Unwrap)
            # a 태그나 label 태그 등도 포함하여 텍스트만 남김
            for tag in content_div.find_all(['span', 'b', 'strong', 'i', 'u', 'font', 'a', 'label']):
                tag.unwrap()

            # 텍스트 추출 (중요: 구분자를 ' '(공백)으로 설정)
            content = content_div.get_text(' ', strip=True)

            # 후처리: 기계적으로 들어간 줄바꿈 정리
            import re
            # 공백+줄바꿈 -> 줄바꿈
            content = re.sub(r'[ \t]*\n[ \t]*', '\n', content)
            # 3개 이상의 연속 줄바꿈 -> 2개로 줄임
            content = re.sub(r'\n{3,}', '\n\n', content)

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
        unique_id = f"{self.site_code}{article_num}"

        created_dt = datetime.now()
        updated_dt = created_dt

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

        date_str_created = self.format_date_str(created_dt)
        date_str_updated = self.format_date_str(updated_dt)

        self.collected_data.append({
            'unique_id': unique_id,
            'title': title_text,
            'content': content,
            'original_url': self.driver.current_url,
            'created_at': date_str_created,
            'updated_at': date_str_updated,
            'vendor_id': self.vendor_id,
            'category_id': cat_id
        })
        self.log(f"Collected: {title_text[:30]}... (ID: {unique_id})", "COLLECT")