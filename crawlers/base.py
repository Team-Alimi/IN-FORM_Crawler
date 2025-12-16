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

        # [리팩터링] 자식들이 매번 계산하지 않게 여기서 미리 계산
        self.limit_date = self.get_limit_date()

    # [리팩터링] 모든 크롤러가 공통으로 사용할 로그 출력 함수 추가
    def log(self, message, level="INFO"):
        icon = "📄"
        if level == "START": icon = "🚀"
        elif level == "SUCCESS": icon = "✅"
        elif level == "WARN": icon = "⚠️"
        elif level == "ERROR": icon = "🔥"
        elif level == "STOP": icon = "🛑"
        elif level == "COLLECT": icon = "✨"

        print(f"{icon} [{self.site_name}] {message}")

    def _init_driver(self):
        """브라우저 드라이버 초기화 및 옵션 설정"""
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-gpu")
        options.add_argument("--blink-settings=imagesEnabled=false")
        options.add_argument("--disable-dev-shm-usage")

        if self.driver_path:
            service = Service(executable_path=self.driver_path)
        else:
            service = Service(ChromeDriverManager().install())

        self.driver = webdriver.Chrome(service=service, options=options)
        self.wait = WebDriverWait(self.driver, 10)

    def run(self):
        """
        [수정됨]
        1. 크롤링 수행
        2. 중복 처리(process_data)는 하지 않음 (Main에서 순차적으로 하기 위해)
        3. 수집된 '사이트 이름'과 '데이터 리스트'를 튜플로 반환
        """
        try:
            self._init_driver()
            self.crawl()

            # [핵심 변경]
            # 데이터를 가공하거나 저장하지 않고, 수집된 원본(collected_data)을 그대로 반환합니다.
            print(f"   🚩 [{self.site_name}] 크롤링 종료. 수집된 데이터: {len(self.collected_data)}건")
            return self.site_name, self.collected_data

        except Exception as e:
            print(f"❌ [{self.site_name}] 실행 중 치명적 오류: {e}")
            # 에러가 나도 프로그램이 죽지 않게 빈 리스트를 반환
            return self.site_name, []

        finally:
            # 드라이버는 여기서 안전하게 종료
            self.close()

    def process_data(self):
        deduper = Deduplicator(self.site_name)
        return deduper.process_batch(self.collected_data)

    def crawl(self):
        raise NotImplementedError

    # ================= [공통 유틸리티] =================

    def get_limit_date(self):
        """n개월 전 1일 날짜 반환 (시간 00:00:00)"""
        now = datetime.now()
        limit = now - relativedelta(months=2)
        return limit.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    def parse_date_raw(self, date_text):
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
        if date_obj is None: return None
        return date_obj.strftime("%Y-%m-%d")

    def match_category(self, title_text):
        if not title_text: return None
        title_lower = title_text.lower()

        exclude_keywords = KEYWORD_CATEGORIES.get(0, [])
        for ex_kw in exclude_keywords:
            if not ex_kw or not ex_kw.strip(): continue
            if ex_kw.lower() in title_lower: return None

        for cat_id, keywords in KEYWORD_CATEGORIES.items():
            if cat_id == 0: continue
            for kw in keywords:
                if not kw or not kw.strip(): continue
                if kw.lower() in title_lower:
                    # self.log(f"키워드 매칭 성공: '{kw}'", "INFO") # 디버깅용
                    return cat_id
        return None

    def wait_element(self, by, selector, timeout=10):
        return WebDriverWait(self.driver, timeout).until(
            EC.presence_of_element_located((by, selector))
        )

    def wait_elements(self, by, selector, timeout=10):
        return WebDriverWait(self.driver, timeout).until(
            EC.presence_of_all_elements_located((by, selector))
        )

    def js_click(self, element):
        self.driver.execute_script("arguments[0].scrollIntoView(true);", element)
        self.driver.execute_script("arguments[0].click();", element)