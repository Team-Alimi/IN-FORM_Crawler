import time
import re
from datetime import datetime
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from .base import BaseCrawler


class TypeECrawler(BaseCrawler):

    def crawl(self):
        # [리팩터링] self.log 사용
        self.log("Type E 크롤링 시작", "START")

        target_tabs = [1, 2]

        for tab_id in target_tabs:
            self.log(f"Tab {tab_id} 진입...")
            page = 1
            stop_tab = False
            prev_page_titles = []

            while True:
                separator = '&' if '?' in self.url else '?'
                current_url = f"{self.url}{separator}prodiv={tab_id}&rp={page}"

                self.log(f"Page {page} 스캔 중...")
                self.driver.get(current_url)

                try:
                    self.wait_element(By.CSS_SELECTOR, '#programZone, span.align-center', timeout=5)
                except:
                    self.log(f"Tab {tab_id} 완료 (로딩 실패/끝).", "SUCCESS")
                    break

                soup = BeautifulSoup(self.driver.page_source, 'html.parser')

                total_cnt = 0
                total_elem = soup.select_one('#pcTit span')
                if total_elem:
                    match = re.search(r'\d+', total_elem.get_text(strip=True))
                    if match:
                        total_cnt = int(match.group())

                empty_msg = soup.select_one('span.align-center')
                if empty_msg and "내 프로그램이 없습니다" in empty_msg.get_text():
                    self.log(f"Tab {tab_id} 완료 (안내 문구).", "SUCCESS")
                    break

                items = soup.select('ul.d-flex-program-list > li')
                if not items:
                    self.log(f"Tab {tab_id} 완료 (아이템 없음).", "SUCCESS")
                    break

                current_titles = []
                for item in items:
                    t_div = item.select_one('div[id$="_Title_txt"]')
                    if t_div: current_titles.append(t_div.get_text(strip=True))

                if current_titles and current_titles == prev_page_titles:
                    self.log(f"Tab {tab_id} 완료 (중복 페이지 감지).", "SUCCESS")
                    break
                prev_page_titles = current_titles

                collected_count = 0

                for i, item in enumerate(items):
                    article_num = total_cnt - ((page - 1) * 10) - i
                    unique_id = f"{self.site_code}{tab_id}{article_num}"

                    status_span = item.select_one('span[name="finishDate"]')
                    if status_span and "마감" in status_span.get_text():
                        self.log("'마감' 발견. Tab 종료.", "STOP")
                        stop_tab = True
                        break

                    title_div = item.select_one('div[id$="_Title_txt"]')
                    if not title_div: continue
                    title_text = title_div.get_text(strip=True)

                    edu_div = item.select_one('div[id$="_eduArea"]')
                    start_str, due_str = None, None

                    if edu_div:
                        date_span = edu_div.select_one('span.bold')
                        if date_span and '~' in date_span.get_text(strip=True):
                            parts = date_span.get_text(strip=True).split('~')
                            s_obj = self.parse_date_raw(parts[0])
                            e_obj = self.parse_date_raw(parts[1])

                            start_str = self.format_date_str(s_obj)
                            due_str = self.format_date_str(e_obj)

                    cat_id = self.match_category(title_text)
                    if cat_id is None: continue

                    try:
                        css_selector = f"#programZone ul.d-flex-program-list > li:nth-of-type({i + 1}) div[id$='_Title_txt']"
                        click_target = self.wait_element(By.CSS_SELECTOR, css_selector, timeout=5)

                        main_window = self.driver.current_window_handle
                        original_windows = self.driver.window_handles

                        self.js_click(click_target)

                        WebDriverWait(self.driver, 10).until(EC.new_window_is_opened(original_windows))
                        new_window = [w for w in self.driver.window_handles if w != main_window][-1]
                        self.driver.switch_to.window(new_window)
                        time.sleep(1.5)

                        self._parse_detail_page(title_text, start_str, due_str, cat_id, unique_id)
                        collected_count += 1

                        self.driver.close()
                        self.driver.switch_to.window(main_window)
                        time.sleep(0.5)

                    except Exception as e:
                        self.log(f"상세 진입 실패 ({title_text}): {e}", "WARN")
                        if self.driver.current_window_handle != main_window:
                            self.driver.close()
                            self.driver.switch_to.window(main_window)
                        time.sleep(2)

                if stop_tab: break
                if collected_count == 0:
                    self.log(f"(Page {page}: 수집된 글 없음)")

                page += 1
                if page > 500: break

    def _parse_detail_page(self, title_text, start_str, due_str, cat_id, unique_id):
        soup = BeautifulSoup(self.driver.page_source, 'html.parser')

        # [수정] 선택 로직 후 unwrap 적용
        content_div = soup.select_one('.viewcontent span.Info')
        if not content_div:
            content_div = soup.select_one('.viewcontent')

        content = ""
        if content_div:
            # [1] <br> -> \n
            for br in content_div.find_all('br'):
                br.replace_with('\n')

            # [2] 블록 태그 뒤에 \n 추가
            for block in content_div.find_all(['p', 'div', 'li', 'tr']):
                block.append('\n')

            # [3] 인라인 태그 unwrap
            for tag in content_div.find_all(['span', 'b', 'strong', 'i', 'u', 'font', 'a', 'label']):
                tag.unwrap()

            # [4] 텍스트 추출 (구분자: 공백)
            content = content_div.get_text(' ', strip=True)

            # [5] 정규식 정리
            import re
            content = re.sub(r'[ \t]*\n[ \t]*', '\n', content)
            content = re.sub(r'\n{3,}', '\n\n', content)

        if not content:
            self.log(f"본문 없음 (Skip): {title_text[:30]}...", "WARN")
            return

        now_str = self.format_date_str(datetime.now())

        self.collected_data.append({
            'unique_id': unique_id,
            'title': title_text,
            'content': content,
            'original_url': self.driver.current_url,
            'created_at': now_str,
            'updated_at': now_str,
            'start_date': start_str,
            'due_date': due_str,
            'vendor_id': self.vendor_id,
            'category_id': cat_id
        })
        self.log(f"Collected: {title_text[:30]}... (ID: {unique_id})", "COLLECT")