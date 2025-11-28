import json
import os
import traceback
from datetime import datetime
from dateutil.relativedelta import relativedelta

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

from config import DATA_ROOT, HISTORY_DIR, KEYWORD_CATEGORIES
from dataprepper.deduplicate import Deduplicator


class BaseCrawler:

    def __init__(self, site_info):
        self.site_name = site_info['name']
        self.site_code = site_info['code']
        self.url = site_info['url']
        self.vendor_id = site_info.get('vendor_id', 0)
        self.driver_path = site_info.get('driver_path')
        self.driver = None
        self.collected_data = []
        self.wait = None

    def _init_driver(self):
        """브라우저 드라이버 초기화 및 옵션 설정"""
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-gpu")
        options.add_argument("--blink-settings=imagesEnabled=false")
        options.add_argument("--disable-dev-shm-usage")

        """전달받은 경로가 있으면 그것을 사용 (충돌 방지)"""
        if self.driver_path:
            service = Service(executable_path=self.driver_path)
        else:
            """경로가 없으면(단독 테스트 등) 직접 설치 (기존 방식)"""
            service = Service(ChromeDriverManager().install())

        self.driver = webdriver.Chrome(service=service, options=options)
        self.wait = WebDriverWait(self.driver, 10)

    def run(self):
        """
        크롤링 및 중복 제거 후 결과 리스트 반환
        """
        inserts = []
        updates = []

        try:
            self._init_driver()
            self.crawl()

            if self.collected_data:
                # 중복 제거 수행 후 결과 받기
                inserts, updates = self.process_data()
            else:
                print(f"⚠️ [{self.site_name}] 수집된 데이터가 없습니다.")

        except NotImplementedError:
            print(f"🔥 [{self.site_name}] 개발자 오류: crawl 메서드 미구현")
        except Exception as e:
            print(f"🔥 [{self.site_name}] 상세 에러 리포트:\n{traceback.format_exc()}")
        finally:
            if self.driver:
                try:
                    self.driver.quit()
                except:
                    pass

        # 메인 프로세스로 결과 반환
        return inserts, updates

    def process_data(self):
        print(f"⚙️ [{self.site_name}] 데이터 분류(Deduplication) 중...")
        deduper = Deduplicator(self.site_name)
        return deduper.process_batch(self.collected_data)

    def crawl(self):
        raise NotImplementedError


    # ================= [공통 유틸리티] =================


    def get_limit_date(self):
        """n개월 전 1일 날짜 반환 (시간 00:00:00)"""
        now = datetime.now()
        limit = now - relativedelta(months=2) # 크롤링 대상 시점 범위 지정(기본값: 2달)
        return limit.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    def parse_date_raw(self, date_text):
        """다양한 날짜 문자열을 datetime 객체로 변환 (시간 정보 제거)"""
        if not date_text: return None
        date_text = date_text.strip()

        formats = [
            '%Y.%m.%d',  # Type A
            '%Y-%m-%d',  # Type B
            '%Y.%m.%d %H:%M',  # Type C
            '%Y/%m/%d'
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(date_text, fmt)
                return dt.replace(hour=0, minute=0, second=0, microsecond=0)
            except ValueError:
                continue
        return None

    def format_date_str(self, date_obj):
        """datetime 객체를 DB 저장용 'YYYY-MM-DD' 문자열로 변환"""
        if date_obj is None: return None
        return date_obj.strftime("%Y-%m-%d")

    def match_category(self, title_text):
        """
        제목에서 키워드를 검사하여 카테고리 ID 반환
        """
        if not title_text: return None

        """제외 키워드(Cat 0) 체크"""
        exclude_keywords = KEYWORD_CATEGORIES.get(0, [])
        for ex_kw in exclude_keywords:
            if ex_kw in title_text:
                return None

        """포함 키워드(Cat 1, 2, 3...) 체크"""
        for cat_id, keywords in KEYWORD_CATEGORIES.items():
            if cat_id == 0: continue  # 0번은 위에서 처리함

            for kw in keywords:
                if kw in title_text:
                    # (디버깅용) 어떤 단어 때문에 매칭되었는지 확인하고 싶다면 주석 해제
                    print(f"   🎯 키워드 매칭 성공: '{kw}' -> {title_text[:20]}...")
                    return cat_id

        return None

    def wait_element(self, by, selector, timeout=10):
        """단일 요소 대기 및 반환"""
        return WebDriverWait(self.driver, timeout).until(
            EC.presence_of_element_located((by, selector))
        )

    def wait_elements(self, by, selector, timeout=10):
        """복수 요소 대기 및 반환"""
        return WebDriverWait(self.driver, timeout).until(
            EC.presence_of_all_elements_located((by, selector))
        )

    def js_click(self, element):
        """JavaScript 강제 클릭"""
        self.driver.execute_script("arguments[0].scrollIntoView(true);", element)
        self.driver.execute_script("arguments[0].click();", element)