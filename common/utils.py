from datetime import datetime
from dateutil.relativedelta import relativedelta
from config import KEYWORD_CATEGORIES

def get_limit_date():
    """과도한 과거 데이터 수집을 방지하고 시스템 리소스를 최적화하기 위한 기준일을 설정함"""
    now = datetime.now()
    limit = now - relativedelta(months=2) # GEMINI.md 지침에 따라 2개월로 설정
    return limit.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

def parse_date_raw(date_text):
    """다양한 형식의 날짜 문자열을 datetime 객체로 변환하여 시스템 표준 형식을 유지함"""
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
    """datetime 객체를 표준 문자열 형식(YYYY-MM-DD)으로 변환하여 DB 정합성을 확보함"""
    if date_obj is None: return None
    return date_obj.strftime("%Y-%m-%d")

def is_excluded(title):
    """사전에 정의된 제외 키워드를 검사하여 정보 가치가 낮은 데이터의 유입을 원천 차단함"""
    if not title: return True
    title_low = title.lower()
    for ex_kw in KEYWORD_CATEGORIES.get(0, []):
        if ex_kw and ex_kw.strip().lower() in title_low: return True
    return False

def process_article(article):
    """모든 크롤러에서 공통적으로 요구되는 텍스트 정제 및 유효성 검사 표준을 강제함"""
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
