import json
import os
import re as regex
import scrapy
from datetime import datetime
from crawlers.scrapy_app.items import InformItem
from crawlers.scrapy_app.utils import get_limit_date, parse_date_raw, format_date_str

class TypeASpider(scrapy.Spider):
    name = 'type_a'
    
    def __init__(self, *args, **kwargs):
        super(TypeASpider, self).__init__(*args, **kwargs)
        
        # Priority 1: Environment Variable (Safest for complex JSON)
        site_info_json = os.environ.get('SCRAPY_SITE_INFO')
        site_info = None

        if site_info_json:
            try:
                site_info = json.loads(site_info_json)
            except json.JSONDecodeError:
                self.logger.error(f"Failed to parse SCRAPY_SITE_INFO: {site_info_json}")
        
        # Priority 2: Scrapy Arguments (Fallback)
        if not site_info:
            if 'site_info_json' in kwargs:
                 try:
                    site_info = json.loads(kwargs['site_info_json'])
                 except:
                    pass
            
            if not site_info:
                name = kwargs.get('name')
                url = kwargs.get('url')
                if name and url:
                    site_info = {
                        'name': name,
                        'code': kwargs.get('code'),
                        'url': url,
                        'vendor_id': int(kwargs.get('vendor_id', 0))
                    }

        if site_info:
            self.site_name = site_info['name']
            self.site_code = site_info['code']
            self.start_urls = [site_info['url']]
            self.vendor_id = site_info.get('vendor_id', 0)
        else:
            self.logger.error("No site_info provided!")
            self.site_name = "Unknown"
            self.start_urls = []
            
        self.limit_date = get_limit_date()
        self.current_page = 1
        self.old_streak = 0

    def parse(self, response):
        # Extract total pages if available
        self.logger.info(f"🚩 [Spider] {self.site_name} - Page {self.current_page} 분석 중... (URL: {response.url})")
        total_pages_text = response.css('._totPage::text').get()
        total_pages = 1000 # Default to high number if not found
        if total_pages_text and total_pages_text.isdigit():
            total_pages = int(total_pages_text)

        # Try multiple selectors for robustness
        rows = response.css('tbody tr')
        if not rows:
            rows = response.css('table tr')
        if not rows:
            rows = response.css('tr')
            
        if not rows:
            self.logger.info("No rows found on page.")
            return

        collected_count = 0
        regular_rows_on_page = 0
        
        for row in rows:
            # Detect if it's a notice (headline) item
            # Notices usually have no number in _artclTdNum (they have an icon/text instead)
            # OR they have a specific class like 'headline' or 'notice'
            num_text = row.css('._artclTdNum::text').get(default='').strip()
            is_notice = not num_text.isdigit()
            
            if not is_notice:
                regular_rows_on_page += 1

            date_text = row.css('._artclTdRdate::text').get()
            
            # Improved Title Extraction
            title_cell = row.css('._artclTdTitle')
            if title_cell:
                title_text = "".join(title_cell.xpath('.//text()').getall()).strip()
            else:
                title_text = None
            
            if not date_text or not title_text:
                continue

            date_text = date_text.strip()
            title_text = regex.sub(r'\s+', ' ', title_text)
            
            date_obj = parse_date_raw(date_text)
            if date_obj is None:
                continue

            # Streak logic: only for regular items
            if not is_notice:
                if date_obj < self.limit_date:
                    self.old_streak += 1
                    if self.old_streak >= 20:
                        self.logger.info("Date limit reached.")
                        return
                    continue
                else:
                    self.old_streak = 0

            # Detail Link
            link = row.css('._artclTdTitle a::attr(href)').get()
            if link:
                yield response.follow(link, callback=self.parse_detail, cb_kwargs={
                    'title': title_text,
                    'num_text': num_text
                })
                # Only count regular items for pagination progress
                if not is_notice:
                    collected_count += 1

        if collected_count == 0:
            self.logger.debug(f"Page {self.current_page}: No new regular items collected (some might have been dropped or were too old).")

        # Stop if we are past total pages or no regular items found at all (end of board)
        if self.current_page >= total_pages or self.current_page >= 100:
            self.logger.info(f"Reached page limit (Current: {self.current_page}, Total: {total_pages}).")
            return
            
        if regular_rows_on_page == 0 and self.current_page > 1:
            self.logger.info("No regular rows found on this page. Stopping.")
            return

        self.current_page += 1
        
        # Pagination
        next_page_link = response.xpath(f'//a[contains(text(), "{self.current_page}")]/@href').get()
        
        if next_page_link:
             if 'javascript' in next_page_link or '#' in next_page_link:
                 if '?' in response.url:
                     if 'page=' in response.url:
                         next_url = regex.sub(r'page=\d+', f'page={self.current_page}', response.url)
                     else:
                         next_url = response.url + f'&page={self.current_page}'
                 else:
                     next_url = response.url + f'?page={self.current_page}'
                 yield scrapy.Request(next_url, callback=self.parse)
             else:
                 yield response.follow(next_page_link, callback=self.parse)
        else:
             # Fallback query string logic
             # If we still have regular rows on this page, or we haven't hit the old_streak limit, try next page
             if regular_rows_on_page > 0 or self.old_streak < 20:
                 if '?' in response.url:
                     if 'page=' in response.url:
                         next_url = regex.sub(r'page=\d+', f'page={self.current_page}', response.url)
                     else:
                         next_url = response.url + f'&page={self.current_page}'
                 else:
                     next_url = response.url + f'?page={self.current_page}'
                 
                 yield scrapy.Request(next_url, callback=self.parse)

    def parse_detail(self, response, title, num_text):
        content_div = response.css('.artclView')
        if not content_div:
            return

        html = content_div.get()
        
        # Replace <br> and block endings with newlines
        html = regex.sub(r'<br\s*/?>', '\n', html, flags=regex.IGNORECASE)
        html = regex.sub(r'</(p|div|li|tr)>', '\n', html, flags=regex.IGNORECASE)
        
        # Remove tags
        clean_text = regex.sub(r'<[^>]+>', ' ', html)
        
        # Cleanup whitespace
        content = regex.sub(r'[ \t]*\n[ \t]*', '\n', clean_text)
        content = regex.sub(r'\n{3,}', '\n\n', content).strip()
        
        if not content:
            return

        article_num = num_text
        
        head_dls = response.css('.artclViewHead .left dl')
        for dl in head_dls:
            dt = dl.css('dt::text').get()
            if dt and '글번호' in dt:
                dd = dl.css('dd::text').get()
                if dd:
                    article_num = dd.strip()
                    break
        
        unique_id = f"{self.site_code}{article_num}"
        
        created_at = format_date_str(datetime.now())
        updated_at = created_at
        
        all_dls = response.css('.artclViewHead dl')
        for dl in all_dls:
            dt = dl.css('dt::text').get(default='').strip()
            dd = dl.css('dd::text').get(default='').strip()
            
            date_obj = parse_date_raw(dd)
            if date_obj:
                if '작성일' in dt:
                    created_at = format_date_str(date_obj)
                elif '수정일' in dt:
                    updated_at = format_date_str(date_obj)

        item = InformItem()
        item['unique_id'] = unique_id
        item['title'] = title
        item['content'] = content
        item['original_url'] = response.url
        item['created_at'] = created_at
        item['updated_at'] = updated_at
        item['vendor_id'] = self.vendor_id
        
        yield item