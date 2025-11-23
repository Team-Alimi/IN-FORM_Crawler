import json
import os
import traceback
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

# main.py 실행 기준이므로 root의 config를 바로 찾을 수 있음
from config import DATA_DIR


class BaseCrawler:
    def __init__(self, site_info):
        self.site_name = site_info['name']
        self.url = site_info['url']
        self.vendor_id = site_info.get('vendor_id', 0)
        self.driver = None
        self.collected_data = []

    def _init_driver(self):
        options = Options()
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