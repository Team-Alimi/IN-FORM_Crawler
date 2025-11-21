import time
import json
import os
import traceback
import re
from datetime import datetime
from dateutil.relativedelta import relativedelta

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

# config.py에서 변수들 가져오기
from config import DATA_DIR, KEYWORD_CATEGORIES


class BaseCrawler:
    def __init__(self, site_info):
        self.site_name = site_info['name']
        self.url = site_info['url']
        self.vendor_id = site_info.get('vendor_id', 0)  # 없을 경우 대비 안전장치
        self.driver = None
        self.collected_data = []

    def _init_driver(self):
        options = Options()
        # 디버깅을 위해 Headless 잠시 주석 처리 (필요하면 주석 해제)
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-gpu")
        options.add_argument("--blink-settings=imagesEnabled=false")

        self.driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

    def save_to_json(self):
        if not self.collected_data:
            print(f"⚠️ [{self.site_name}] 수집된 데이터가 없어 파일을 생성하지 않습니다.")
            return

        file_path = os.path.join(DATA_DIR, f"{self.site_name}.json")
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(self.collected_data, f, ensure_ascii=False, indent=4)
            print(f"💾 [{self.site_name}] JSON 저장 완료 ({len(self.collected_data)}건) -> {file_path}")
        except Exception as e:
            print(f"❌ [{self.site_name}] JSON 저장 실패: {e}")

    def run(self):
        self._init_driver()
        try:
            # 자식 클래스에 구현된 crawl 메서드 실행
            self.crawl()
        except NotImplementedError:
            print(f"🔥 [{self.site_name}] 개발자 오류: crawl 메서드가 구현되지 않았습니다.")
        except Exception as e:
            print(f"🔥 [{self.site_name}] 상세 에러 리포트:\n{traceback.format_exc()}")
        finally:
            self.save_to_json()
            if self.driver: self.driver.quit()

    def crawl(self):
        # 이 메서드는 자식 클래스(TypeACrawler 등)에서 반드시 덮어써야 함
        raise NotImplementedError


class TypeACrawler(BaseCrawler):
    def crawl(self):
        self.driver.get(self.url)
        time.sleep(3)

        # 날짜 제한 계산 (현재 - 2개월)
        now = datetime.now()
        limit_date = now - relativedelta(months=2)
        limit_date = limit_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        print(f"🔍 [{self.site_name}] 크롤링 시작 (Limit: {limit_date.strftime('%Y-%m-%d')})")

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
                # 1. 날짜 & 제목 추출
                date_cell = row.select_one('._artclTdRdate')
                title_cell = row.select_one('._artclTdTitle')

                if not date_cell or not title_cell:
                    continue

                date_text = date_cell.get_text(strip=True)
                title_text = title_cell.get_text(strip=True)

                # 2. 날짜 검증
                try:
                    article_date = datetime.strptime(date_text, '%Y.%m.%d')

                    if article_date < limit_date:
                        consecutive_old_posts += 1
                        # 상단 고정 공지가 많을 수 있으므로 20회로 넉넉하게 설정
                        if consecutive_old_posts >= 20:
                            print(f"🛑 [{self.site_name}] 날짜 제한 도달 (연속 20회 구형 글 발견). 진짜 종료합니다.")
                            return

                            # print(f"   Pass: {title_text[:10]}... ({date_text}) - 오래된 글")
                        continue
                    else:
                        consecutive_old_posts = 0
                except ValueError:
                    continue

                    # 3. 키워드 검증
                matching_category = None
                # KEYWORD_CATEGORIES를 순회하며 키워드를 검증하고, 일치하면 카테고리를 저장합니다.
                for category, keywords in KEYWORD_CATEGORIES.items():
                    if any(keyword in title_text for keyword in keywords):
                        matching_category = category
                        break

                # 일치하는 키워드가 없어 matching_category가 None이면 다음 게시글로 스킵
                if not matching_category:
                    continue

                    # 4. 상세 수집 시작
                try:
                    #  텍스트 검색 대신, '몇 번째 줄(i+1)'에 있는 링크인지 정확한 위치(XPath)로 클릭
                    # XPath 설명: //tbody의 (i+1)번째 tr 안에 있는 -> ._artclTdTitle 클래스를 가진 td 안의 -> a 태그
                    # (i는 0부터 시작하므로 XPath에서는 i+1을 해야 함)
                    xpath = f'//tbody/tr[{i + 1}]/td[contains(@class, "_artclTdTitle")]/a'

                    link = self.driver.find_element(By.XPATH, xpath)

                    # 화면에 안 보이면 스크롤해서 클릭
                    self.driver.execute_script("arguments[0].scrollIntoView(true);", link)
                    self.driver.execute_script("arguments[0].click();", link)  # JS로 강제 클릭 (더 안정적)

                    time.sleep(1)

                    # 상세 페이지 파싱
                    self._parse_detail_page(title_text, matching_category)
                    page_processed_count += 1

                    # 뒤로 가기
                    self.driver.back()
                    time.sleep(1)

                except Exception as e:
                    print(f"⚠️ 상세 진입 실패 ({title_text}): {e}")
                    # 에러 나면 안전하게 목록으로 다시 로드
                    self.driver.get(self.url)
                    time.sleep(2)

            if page_processed_count == 0:
                print(f"   (ℹ️ {page} 페이지: 수집된 글 없음)")

            # 5. 다음 페이지 이동
            page += 1
            try:
                next_btn = self.driver.find_element(By.XPATH, f'//a[contains(@onclick, "page") and text()="{page}"]')
                next_btn.click()
                time.sleep(2)
            except:
                print(f"✅ [{self.site_name}] 마지막 페이지 도달.")
                break

    def _parse_detail_page(self, list_title,category):
        soup = BeautifulSoup(self.driver.page_source, 'html.parser')

        # 본문
        content_div = soup.select_one('.artclView')
        content = content_div.get_text('\n', strip=True) if content_div else ""

        # 작성일, 수정일 추출
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
                created_at = val.replace('.', '-')
            elif '수정일' in label:
                updated_at = val.replace('.', '-')

        # 리스트에 저장
        self.collected_data.append({
            'title': list_title,
            'content': content,
            'original_url': self.driver.current_url,
            'created_at': created_at,
            'updated_at': updated_at,
            'vendor_id': self.vendor_id,
            'category': category
        })
        print(f"   ---> 수집 성공: {list_title} (Category: {category})")


class TypeBCrawler(BaseCrawler):
    def crawl(self):
        print(f"[{self.site_name}] Type B 크롤러는 아직 구현되지 않았습니다.")
        pass