import json
import os
import re as regex
import scrapy
from datetime import datetime
from crawlers.scrapy_app.items import InformItem
from common.utils import get_limit_date, parse_date_raw, format_date_str
from common.logger import log_status

class TypeASpider(scrapy.Spider):
    """인하대 표준 게시판(Type A) 수집용 스파이더"""
    name = 'type_a'
    
    def __init__(self, *args, **kwargs):
        super(TypeASpider, self).__init__(*args, **kwargs)
        
        site_info_json = os.environ.get('SCRAPY_SITE_INFO')
        site_info = json.loads(site_info_json) if site_info_json else None
        
        if site_info:
            self.site_name, self.site_code = site_info['name'], site_info['code']
            self.start_urls, self.vendor_id = [site_info['url']], site_info.get('vendor_id', 0)
        else:
            self.site_name, self.start_urls = "Unknown", []
            
        self.limit_date = get_limit_date()
        self.current_page, self.old_streak = 1, 0

    def log_msg(self, message, level="INFO"):
        """표준 로그 출력"""
        log_status(self.site_name, message, level)

    def parse(self, response):
        """목록 페이지 수집 (Scrapy 표준 진입점)"""
        return self.collect_article_list(response)

    def collect_article_list(self, response):
        """게시글 목록 추출 및 다음 페이지 이동"""
        self.log_msg(f"Page {self.current_page} 분석 중...", "INFO")

        total_pages_text = response.css('._totPage::text').get()
        total_pages = int(total_pages_text) if (total_pages_text and total_pages_text.isdigit()) else 1000

        rows = response.css('tbody tr, table tr, tr')
        if not rows: return

        regular_rows_on_page = 0
        for row in rows:
            num_text = row.css('._artclTdNum::text').get(default='').strip()
            is_notice = not num_text.isdigit()
            if not is_notice: regular_rows_on_page += 1

            date_text = row.css('._artclTdRdate::text').get()
            title_cell = row.css('._artclTdTitle')
            title_text = "".join(title_cell.xpath('.//text()').getall()).strip() if title_cell else None
            
            if not date_text or not title_text: continue

            date_text, title_text = date_text.strip(), regex.sub(r'\s+', ' ', title_text)
            date_obj = parse_date_raw(date_text)
            if date_obj is None: continue

            if not is_notice:
                if date_obj < self.limit_date:
                    self.old_streak += 1
                    if self.old_streak >= 20:
                        self.log_msg("수집 기한 도달. 종료.", "STOP")
                        return
                    continue
                else: self.old_streak = 0

            link = row.css('._artclTdTitle a::attr(href)').get()
            if link:
                yield response.follow(link, callback=self.collect_article_detail, cb_kwargs={
                    'title': title_text, 'num_text': num_text
                })

        if self.current_page < total_pages and self.current_page < 100:
            if regular_rows_on_page > 0 or self.old_streak < 20:
                self.current_page += 1
                next_url = self._build_next_url(response.url)
                yield scrapy.Request(next_url, callback=self.parse)

    def _build_next_url(self, current_url):
        """페이지 번호 기반 다음 URL 생성"""
        if 'page=' in current_url:
            return regex.sub(r'page=\d+', f'page={self.current_page}', current_url)
        separator = '&' if '?' in current_url else '?'
        return f"{current_url}{separator}page={self.current_page}"

    def collect_article_detail(self, response, title, num_text):
        """상세 페이지 내용 및 이미지 수집"""
        content_div = response.css('.artclView')
        if not content_div: return

        html = content_div.get()
        html = regex.sub(r'<br\s*/?>', '\n', html, flags=regex.IGNORECASE)
        html = regex.sub(r'</(p|div|li|tr)>', '\n', html, flags=regex.IGNORECASE)
        clean_text = regex.sub(r'<[^>]+>', ' ', html)
        content = regex.sub(r'[ \t]*\n[ \t]*', '\n', clean_text)
        content = regex.sub(r'\n{3,}', '\n\n', content).strip()
        
        attachments = []
        img_tags = content_div.css('img::attr(src)').getall()
        for img_src in img_tags:
            attachments.append({'attachment_url': response.urljoin(img_src)})

        if not content and not attachments: return

        article_num = num_text
        for dl in response.css('.artclViewHead .left dl'):
            dt = dl.css('dt::text').get()
            if dt and '글번호' in dt:
                article_num = (dl.css('dd::text').get() or num_text).strip()
                break
        
        created_at = updated_at = format_date_str(datetime.now())
        for dl in response.css('.artclViewHead dl'):
            dt, dd = dl.css('dt::text').get(default='').strip(), dl.css('dd::text').get(default='').strip()
            date_obj = parse_date_raw(dd)
            if date_obj:
                if '작성일' in dt: created_at = format_date_str(date_obj)
                elif '수정일' in dt: updated_at = format_date_str(date_obj)

        article = InformItem()
        article['unique_id'] = f"{self.site_code}{article_num}"
        article['title'], article['content'] = title, content
        article['original_url'] = response.url
        article['created_at'], article['updated_at'] = created_at, updated_at
        article['vendor_id'] = self.vendor_id
        article['site_name'], article['site_code'] = self.site_name, self.site_code
        article['attachments'] = attachments
        
        self.log_msg(f"수집 성공: {title[:20]}... ({len(attachments)} imgs)", "COLLECT")
        yield article
