import json
import os
import sys
import asyncio
import uuid

# Lazy loading of crawlers to avoid unnecessary dependency loading

class TypeACrawler:
    def __init__(self, site_info):
        self.site_info = site_info
        self.site_name = site_info['name']

    async def run(self):
        # Create a temporary filename (relative path to avoid Windows path parsing issues)
        temp_filename = f"temp_scrapy_{uuid.uuid4()}.json"
        
        # Pass site info via environment variable to avoid command line argument parsing issues
        env = os.environ.copy()
        env['SCRAPY_SITE_INFO'] = json.dumps(self.site_info)
        env['SCRAPY_OUTPUT_FILE'] = temp_filename
        
        # Execute the custom runner script directly
        runner_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'run_spider.py')
        args = [sys.executable, runner_script]

        print(f"   🚀 [{self.site_name}] Scrapy 시작 (Async Runner)...")
        
        try:
            process = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                print(f"   ❌ [{self.site_name}] Scrapy 실패 (Code: {process.returncode})")
                print(f"   Stderr: {stderr.decode('utf-8', errors='ignore')}")
                return self.site_name, []

            collected_data = []
            if os.path.exists(temp_filename):
                try:
                    with open(temp_filename, 'r', encoding='utf-8') as f:
                        collected_data = json.load(f)
                except json.JSONDecodeError:
                    pass
                finally:
                    try:
                        os.remove(temp_filename)
                    except OSError:
                        pass
            
            print(f"   🛑 [{self.site_name}] Scrapy 종료. 데이터: {len(collected_data)}건")
            return self.site_name, collected_data

        except Exception as e:
            print(f"   ❌ [{self.site_name}] 에러 발생: {e}")
            if os.path.exists(temp_filename):
                try:
                    os.remove(temp_filename)
                except OSError:
                    pass
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

# Alias for compatibility (Type D merged into Type C logic)
TypeDCrawler = TypeCCrawler

class TypeECrawler:
    def __init__(self, site_info): pass
    async def run(self): return "Type E", []
