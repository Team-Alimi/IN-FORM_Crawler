import re as regex
from datetime import datetime
from dateutil.relativedelta import relativedelta
from config import KEYWORD_CATEGORIES

def get_limit_date():
    """수집 기한 반환"""
    now = datetime.now()
    limit = now - relativedelta(months=12) # 수집 기한 설정
    return limit.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

def parse_date_raw(date_text):
    """문자열 날짜를 객체로 변환"""
    if not date_text: return None
    date_text = date_text.strip()
    formats = ['%Y.%m.%d', '%Y-%m-%d', '%Y.%m.%d %H:%M', '%Y/%m/%d']
    for fmt in formats:
        try:
            dt = datetime.strptime(date_text, fmt)
            return dt.replace(hour=0, minute=0, second=0, microsecond=0)
        except ValueError: continue
    return None

def format_date_str(date_obj):
    """날짜를 문자열로 변환"""
    if date_obj is None: return None
    return date_obj.strftime("%Y-%m-%d")

def is_excluded(title):
    """제외 키워드 포함 여부 확인"""
    if not title: return True
    title_low = title.lower()
    for ex_kw in KEYWORD_CATEGORIES.get(0, []):
        if ex_kw and ex_kw.strip().lower() in title_low: return True
    return False

def process_article(article):
    """게시글 정제 및 제외 키워드 검증 (순환 참조 방지를 위해 내부 임포트)"""
    if is_excluded(article.get('title', '')): return None

    from dataprepper.text_cleaner import Cleaner
    cleaner = Cleaner()
    
    if article.get('content'):
        article['content'] = cleaner.clean_contents_text(article['content'])
    
    if not all(article.get(f) for f in ['unique_id', 'title', 'original_url']):
        return None
    if not article.get('content') and not article.get('attachments'):
        return None
    return article
