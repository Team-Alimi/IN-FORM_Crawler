import json
import os
import sys
import asyncio
import uuid
from common.logger import log_status

# Lazy loading of crawlers to avoid unnecessary dependency loading

class TypeACrawler:
    """Scrapy 실행을 위한 래퍼 클래스 (Type A 전용)"""
    def __init__(self, site_info):
        self.site_info = site_info
        self.site_name = site_info['name']

    async def run(self):
        """Scrapy 프로세스를 비동기로 실행하고 결과를 JSON으로 읽음"""
        temp_filename = f"temp_scrapy_{uuid.uuid4()}.json"
        
        env = os.environ.copy()
        env['SCRAPY_SITE_INFO'] = json.dumps(self.site_info)
        env['SCRAPY_OUTPUT_FILE'] = temp_filename
        
        runner_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'run_spider.py')
        args = [sys.executable, runner_script]

        log_status(self.site_name, "Scrapy 프로세스 시작", "START")
        
        try:
            process = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                log_status(self.site_name, f"Scrapy 실행 실패 (Code: {process.returncode})", "ERROR")
                return self.site_name, []

            collected_articles = []
            if os.path.exists(temp_filename):
                try:
                    with open(temp_filename, 'r', encoding='utf-8') as f:
                        collected_articles = json.load(f)
                except: pass
                finally:
                    try: os.remove(temp_filename)
                    except: pass
            
            log_status(self.site_name, f"Scrapy 완료 (수집: {len(collected_articles)}건)", "STOP")
            return self.site_name, collected_articles

        except Exception as e:
            log_status(self.site_name, f"실행 중 에러: {e}", "ERROR")
            if os.path.exists(temp_filename):
                try: os.remove(temp_filename)
                except: pass
            return self.site_name, []

class TypeBCrawler:
    def __init__(self, site_info):
        self.site_info = site_info
    async def run(self):
        from .playwright.type_b import TypeBCrawler as InternalCrawler
        return await InternalCrawler(self.site_info).run()

class TypeCCrawler:
    def __init__(self, site_info):
        self.site_info = site_info
    async def run(self):
        from .playwright.type_c import TypeCCrawler as InternalCrawler
        return await InternalCrawler(self.site_info).run()

# Alias for compatibility
TypeDCrawler = TypeCCrawler

class TypeECrawler:
    def __init__(self, site_info): pass
    async def run(self): return "Type E", []
