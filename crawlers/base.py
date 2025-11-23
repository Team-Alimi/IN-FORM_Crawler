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

from config import DATA_DIR, KEYWORD_CATEGORIES


class BaseCrawler:

    def __init__(self, site_info):
        self.site_name = site_info['name']
        self.url = site_info['url']
        self.vendor_id = site_info.get('vendor_id', 0)
        self.driver = None
        self.collected_data = []
        self.wait = None

    def _init_driver(self):
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-gpu")
        options.add_argument("--blink-settings=imagesEnabled=false")

        self.driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        self.wait = WebDriverWait(self.driver, 10)

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
        try:
            self._init_driver()
            self.crawl()
        except NotImplementedError:
            print(f"🔥 [{self.site_name}] 개발자 오류: crawl 메서드 미구현")
        except Exception as e:
            print(f"🔥 [{self.site_name}] 상세 에러 리포트:\n{traceback.format_exc()}")
        finally:
            self.save_to_json()
            if self.driver:
                try:
                    self.driver.quit()
                except:
                    pass

    def crawl(self):
        raise NotImplementedError


    # ================= [공통 유틸리티 메서드] =================


    def get_limit_date(self):
        """2개월 전 1일 날짜 반환 (시간 00:00:00)"""
        now = datetime.now()
        limit = now - relativedelta(months=2)
        return limit.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    def parse_date_raw(self, date_text):
        """
            문자열을 datetime 객체로 변환하되, 시간은 00:00:00으로 초기화
            비교 로직의 일관성을 위해 시간 정보는 제거함
        """
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
                # 시간 정보를 제거하여 비교 및 저장의 일관성 확보
                return dt.replace(hour=0, minute=0, second=0, microsecond=0)
            except ValueError:
                continue
        return None

    def format_date_str(self, date_obj):
        """
            datetime 객체를 DB 저장용 'YYYY-MM-DD' 문자열로 변환
        """
        if date_obj is None:
            return None
        return date_obj.strftime("%Y-%m-%d")

    def match_category(self, title_text):
        """
            제목에서 키워드를 찾아 카테고리 ID 반환
        """
        for cat_id, keywords in KEYWORD_CATEGORIES.items():
            if any(kw in title_text for kw in keywords):
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