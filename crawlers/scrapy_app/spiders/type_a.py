import json
import os
import re as regex
import scrapy
from datetime import datetime
from crawlers.scrapy_app.items import InformArticle
from common.utils import get_limit_date, parse_date_raw, format_date_str
from common.logger import log_status

class TypeASpider(scrapy.Spider):
    """표준 목록 구조를 가진 사이트에서 기한 내 게시글을 효율적으로 추출하는 스파이더"""
    name = 'type_a'
    
    def __init__(self, *args, **kwargs):
        """환경 변수의 사이트 메타데이터를 로드하고 수집 기한 등 실행 환경을 설정함"""
        super(TypeASpider, self).__init__(*args, **kwargs)
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
        tot = int(response.css('._totPage::text').get() or 1000)
        rows = response.css('tbody tr, table tr, tr')
        if not rows: return

        reg_cnt = 0
        for row in rows:
            num = row.css('._artclTdNum::text').get(default='').strip()
            is_pinned = not num.isdigit() # 숫자가 아니면 고정 공지
            if not is_pinned: reg_cnt += 1

            dt_txt = row.css('._artclTdRdate::text').get()
            tit_c = row.css('._artclTdTitle')
            tit = "".join(tit_c.xpath('.//text()').getall()).strip() if tit_c else None
            if not dt_txt or not tit: continue

            dt_obj = parse_date_raw(dt_txt)
            if dt_obj is None: continue

            # 날짜 기한 체크
            if dt_obj < self.limit:
                if not is_pinned:
                    self.streak += 1
                    if self.streak >= 20: 
                        self.log_msg("기한 도달로 인한 종료.", "STOP"); return
                continue # 기한 지난 글 수집 방지
            else:
                if not is_pinned: self.streak = 0

            lnk = row.css('._artclTdTitle a::attr(href)').get()
            if lnk:
                yield response.follow(lnk, callback=self.parse_detail, cb_kwargs={'title': tit, 'num': num})

        if self.page < tot and self.page < 100:
            if reg_cnt > 0 or self.streak < 20:
                self.page += 1
                sep = '&' if '?' in response.url else '?'
                next_url = f"{response.url.split('page=')[0]}page={self.page}" if 'page=' in response.url else f"{response.url}{sep}page={self.page}"
                yield scrapy.Request(next_url, callback=self.parse)

    def parse_detail(self, response, title, num):
        """텍스트 본문과 이미지(포스터 등)를 조합하여 정보의 완전성이 보장된 데이터를 생성함"""
        view = response.css('.artclView')
        if not view: return
        html = view.get()
        html = regex.sub(r'<br\s*/?>', '\n', html, flags=regex.IGNORECASE)
        html = regex.sub(r'</(p|div|li|tr)>', '\n', html, flags=regex.IGNORECASE)
        cnt = regex.sub(r'\n{3,}', '\n\n', regex.sub(r'<[^>]+>', ' ', html)).strip()
        att = [{'attachment_url': response.urljoin(src)} for src in view.css('img::attr(src)').getall()]
        if not cnt and not att: return

        # 글번호 및 날짜 재추출
        art_num = num
        for dl in response.css('.artclViewHead .left dl'):
            if '글번호' in (dl.css('dt::text').get() or ''):
                art_num = (dl.css('dd::text').get() or num).strip(); break
        
        c_at = u_at = format_date_str(datetime.now())
        for dl in response.css('.artclViewHead dl'):
            dt, dd = (dl.css('dt::text').get() or '').strip(), (dl.css('dd::text').get() or '').strip()
            d_obj = parse_date_raw(dd)
            if d_obj:
                if '작성일' in dt: c_at = format_date_str(d_obj)
                elif '수정일' in dt: u_at = format_date_str(d_obj)

        article = InformArticle()
        article['unique_id'], article['title'], article['content'] = f"{self.code}{art_num}", title, cnt
        article['original_url'], article['created_at'], article['updated_at'] = response.url, c_at, u_at
        article['vendor_id'], article['site_name'], article['site_code'] = self.vendor_id, self.name, self.code
        article['attachments'] = att
        self.log_msg(f"수집 성공: {title[:20]}... ({len(att)} imgs)", "COLLECT")
        yield article
