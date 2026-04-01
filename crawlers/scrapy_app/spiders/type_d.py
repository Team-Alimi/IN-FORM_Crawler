import json
import os
import re
import scrapy
from datetime import datetime
from crawlers.scrapy_app.items import InformArticle
from common.utils import get_limit_date, parse_date_raw, format_date_str
from common.logger import log_status

class TypeDSpider(scrapy.Spider):
    """망보드(Mangboard) 등 SSR 기반 목록 구조에서 데이터를 효율적으로 추출하는 스파이더"""
    name = 'type_d'
    
    def __init__(self, *args, **kwargs):
        """환경 변수의 사이트 메타데이터를 로드하고 수집 기한 등 실행 환경을 설정함"""
        super(TypeDSpider, self).__init__(*args, **kwargs)
        inf = json.loads(os.environ.get('SCRAPY_SITE_INFO')) if os.environ.get('SCRAPY_SITE_INFO') else None
        if inf:
            self.name, self.code, self.start_urls = inf['name'], inf['code'], [inf['url']]
            self.vendor_id = inf.get('vendor_id', 0)
        else:
            self.name, self.start_urls = "Unknown", []
        self.limit, self.page, self.streak = get_limit_date(), 1, 0

    def log_msg(self, msg, lv="INFO"):
        """프로젝트 공통 로깅 규격에 맞춰 사이트별 작업 진행 상태를 기록함"""
        log_status(self.name, msg, lv)

    def parse(self, response):
        """목록을 순회하며 기한 초과 시 조기 종료하여 불필요한 네트워크 리소스 낭비를 방지함"""
        self.log_msg(f"Page {self.page} 분석 중...", "INFO")
        rows = response.css('table#tbl_board_list tbody tr')
        if not rows:
            rows = response.css('table tr') # Fallback
        if not rows: return

        reg_cnt = 0
        for i, row in enumerate(rows):
            # 고유 ID 추출
            raw_id = row.css('::attr(id)').get() or ""
            match = re.search(r'\d+$', raw_id)
            num = match.group() if match else str(datetime.now().timestamp())
            
            # 날짜 추출
            dt_txt = "".join(row.css('td:nth-child(2)::text, td:nth-child(2) *::text').getall()).strip()
            dt_obj = parse_date_raw(dt_txt)
            
            # 고정 공지 판정
            has_icon = row.css('img[src*="notice"], span.mb-notice, .mb-notice').get() is not None
            title_link = row.css('td.text-left a')
            title = title_link.css('::attr(title)').get() or "".join(title_link.css('::text').getall())
            title = title.strip()
            is_pinned = has_icon or "[공지]" in title or "[안내]" in title
            
            if not is_pinned and self.page == 1 and i < 10 and dt_obj and dt_obj < self.limit:
                is_pinned = True

            if not is_pinned: reg_cnt += 1
            
            # 기한 검사
            if dt_obj:
                if dt_obj < self.limit:
                    if not is_pinned:
                        self.streak += 1
                        if self.streak >= 20:
                            self.log_msg("기한 도달로 인한 종료.", "STOP")
                            return
                    continue 
                else:
                    if not is_pinned: self.streak = 0

            lnk = title_link.css('::attr(href)').get()
            if lnk:
                yield response.follow(lnk, callback=self.parse_detail, cb_kwargs={
                    'title': title, 
                    'num': num,
                    'dt_obj': dt_obj
                })

        if reg_cnt > 0 or self.streak < 20:
            self.page += 1
            if self.page > 100: return
            
            sep = '&' if '?' in self.start_urls[0] else '?'
            base_url = self.start_urls[0].split('&board_page=')[0]
            next_url = f"{base_url}{sep}board_page={self.page}"
            yield scrapy.Request(next_url, callback=self.parse)

    def parse_detail(self, response, title, num, dt_obj):
        """텍스트 본문과 이미지(포스터 등)를 조합하여 정보의 완전성이 보장된 데이터를 생성함"""
        view = response.css('tr[id*="tr_content"] td, div.board-view-cnt, .view_content, #board_view_content, .mb-content')
        if not view: 
            view = response.css('.board-view')
        if not view: return

        raw_html = view.get()
        att = [{'attachment_url': response.urljoin(src)} for src in view.css('img::attr(src)').getall()]
        if not raw_html and not att: return 

        art_num = num
        c_at = u_at = format_date_str(dt_obj) if dt_obj else format_date_str(datetime.now())

        article = InformArticle()
        article['unique_id'] = f"{self.code}{art_num}"
        article['title'] = title
        article['content'] = raw_html
        article['original_url'] = response.url
        article['created_at'] = c_at
        article['updated_at'] = u_at
        article['vendor_ids'] = [self.vendor_id]
        article['vendor_urls'] = [response.url]
        article['site_name'] = self.name
        article['site_code'] = self.code
        article['attachments'] = att
        
        self.log_msg(f"수집 성공: {title[:20]}... ({len(att)} imgs)", "COLLECT")
        yield article
