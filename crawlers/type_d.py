import time
from datetime import datetime
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup
from .base import BaseCrawler


class TypeDCrawler(BaseCrawler):

    def crawl(self):
        limit_date = self.get_limit_date()
        print(f"🚀 [{self.site_name}] Type D 크롤링 시작 (Limit: {limit_date.strftime('%Y-%m-%d')})")

        target_tabs = [1, 3, 4]

        for tab_id in target_tabs:
            print(f"\n📂 [{self.site_name}] Tab {tab_id} 진입...")
            page = 1
            old_streak = 0
            prev_page_titles = []

            while True:
                separator = '&' if '?' in self.url else '?'
                current_url = f"{self.url}{separator}cate={tab_id}&per_page={page}"

                print(f"📄 [{self.site_name}] Page {page} 스캔 중... (Tab {tab_id})")
                self.driver.get(current_url)

                # [목록 로딩]
                try:
                    self.wait_elements(By.CSS_SELECTOR, 'tbody tr')
                except:
                    print(f"✅ Tab {tab_id} 완료 (글 없음).")
                    break

                soup = BeautifulSoup(self.driver.page_source, 'html.parser')
                rows = soup.select('tbody tr')
                collected_count = 0

                if not rows: break

                # [종료 조건: 안내 문구]
                empty_msg_td = soup.select_one('td.text-center')
                if empty_msg_td and "등록된 게시글이 없습니다" in empty_msg_td.get_text():
                    print(f"✅ Tab {tab_id} 완료 (안내 문구 감지).")
                    break

                # [종료 조건: 중복 페이지 감지]
                current_titles = []
                for r in rows:
                    subj = r.select_one('td.subject span a')
                    if subj: current_titles.append(subj.get_text(strip=True))

                if current_titles and current_titles == prev_page_titles:
                    print(f"✅ Tab {tab_id} 완료 (중복 페이지 감지).")
                    break
                prev_page_titles = current_titles

                for i, row in enumerate(rows):
                    # [데이터 추출]
                    subject_td = row.select_one('td.subject')
                    date_td = row.select_one('td.regdate')
                    if not subject_td or not date_td: continue

                    title_anchor = subject_td.select_one('a')
                    date_span = date_td.select_one('span')
                    if not title_anchor or not date_span: continue

                    title_text = title_anchor.get_text(strip=True)
                    date_text = date_span.get_text(strip=True)
                    if not date_text and date_span.has_attr('title'):
                        date_text = date_span['title']

                    # [날짜 검증]
                    date_obj = self.parse_date_raw(date_text)
                    if date_obj is None: continue

                    if date_obj < limit_date:
                        old_streak += 1
                        if old_streak >= 20:
                            print(f"🛑 [{self.site_name}] 날짜 제한 도달. 종료.")
                            break
                        continue
                    else:
                        old_streak = 0

                    # [키워드 매칭]
                    cat_id = self.match_category(title_text)
                    if cat_id is None: continue

                    # [글번호 임시 매칭]
                    num_cell = row.select_one('._artclTdNum')
                    num_text = num_cell.get_text(strip=True)

                    # [상세 진입]
                    try:
                        xpath = f'//tbody/tr[{i + 1}]/td[contains(@class, "subject")]//a'
                        link = self.driver.find_element(By.XPATH, xpath)
                        self.js_click(link)
                        time.sleep(1)

                        self._parse_detail_page(title_text, date_obj, cat_id, tab_id, num_text)
                        collected_count += 1

                        self.driver.back()
                        time.sleep(1)
                    except Exception as e:
                        print(f"⚠️ [{self.site_name}] 상세 진입 실패: {e}")
                        self.driver.get(current_url)
                        time.sleep(2)

                if old_streak >= 20: break
                if collected_count == 0:
                    print(f"   (ℹ️ Page {page}: 수집된 글 없음)")

                page += 1
                if page > 500:
                    print("🛑 페이지 과다. 강제 종료.")
                    break

    def _parse_detail_page(self, title_text, date_obj, cat_id, tab_id, num_text):
        soup = BeautifulSoup(self.driver.page_source, 'html.parser')

        content_div = soup.select_one('.contents_wrap')
        content = content_div.get_text('\n', strip=True) if content_div else ""

        # [내용이 없는 게시글은 패스]
        if not content:
            print(f"   ⚠️ 본문 없음 (Skip): {title_text[:30]}...")
            return

        # [글번호 파싱]
        article_num = num_text

        # 상세 페이지 헤더 왼쪽 영역(.left)에서 글번호 탐색
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

        unique_id = f"{self.site_code}{tab_id}{article_num}"

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
        print(f"   ✨ Collected: {title_text[:30]}...")