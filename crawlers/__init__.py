import json
import os
import sys
import asyncio
import uuid
from common.logger import log_status

class TypeACrawler:
    """Scrapy 실행 래퍼"""
    def __init__(self, site):
        self.site = site
        self.name = site['name']

    async def run(self):
        tmp = f"temp_scrapy_{uuid.uuid4()}.json"
        env = os.environ.copy()
        env['SCRAPY_SITE_INFO'] = json.dumps(self.site)
        env['SCRAPY_OUTPUT_FILE'] = tmp
        
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'run_spider.py')
        log_status(self.name, "Scrapy 시작", "START")
        
        try:
            proc = await asyncio.create_subprocess_exec(sys.executable, script, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env)
            await proc.communicate()
            
            data = []
            if os.path.exists(tmp):
                try:
                    with open(tmp, 'r', encoding='utf-8') as f: data = json.load(f)
                except: pass
                finally:
                    try: os.remove(tmp)
                    except: pass
            
            log_status(self.name, f"Scrapy 완료 ({len(data)}건)", "STOP")
            return self.name, data
        except Exception as e:
            log_status(self.name, f"에러: {e}", "ERROR")
            if os.path.exists(tmp):
                try: os.remove(tmp)
                except: pass
            return self.name, []

class TypeBCrawler:
    """Playwright Type B 래퍼"""
    def __init__(self, site): self.site = site
    async def run(self):
        try:
            from crawlers.playwright.type_b import TypeBCrawler as InternalCrawler
            crawler_inst = InternalCrawler(self.site)
            return await crawler_inst.run()
        except Exception as e:
            log_status(self.site['name'], f"임포트 또는 실행 오류: {e}", "ERROR")
            return self.site['name'], []

class TypeCCrawler:
    """Playwright Type C 래퍼"""
    def __init__(self, site): self.site = site
    async def run(self):
        try:
            from crawlers.playwright.type_c import TypeCCrawler as InternalCrawler
            crawler_inst = InternalCrawler(self.site)
            return await crawler_inst.run()
        except Exception as e:
            log_status(self.site['name'], f"임포트 또는 실행 오류: {e}", "ERROR")
            return self.site['name'], []

TypeDCrawler = TypeCCrawler
class TypeECrawler:
    """Playwright Type E 래퍼"""
    def __init__(self, site): self.site = site
    async def run(self):
        try:
            from crawlers.playwright.type_e import TypeECrawler as InternalCrawler
            crawler_inst = InternalCrawler(self.site)
            return await crawler_inst.run()
        except Exception as e:
            log_status(self.site['name'], f"임포트 또는 실행 오류: {e}", "ERROR")
            return self.site['name'], []
