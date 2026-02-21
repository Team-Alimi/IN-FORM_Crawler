import re as regex
from datetime import datetime
from dateutil.relativedelta import relativedelta
from config import KEYWORD_CATEGORIES

def get_limit_date():
    """n개월 전 1일 날짜 반환 (시간 00:00:00)"""
    now = datetime.now()
    limit = now - relativedelta(months=2) # 2개월 전
    return limit.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

def parse_date_raw(date_text):
    """문자열 날짜를 datetime 객체로 변환"""
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
    """datetime 객체를 YYYY-MM-DD 문자열로 변환"""
    if date_obj is None: return None
    return date_obj.strftime("%Y-%m-%d")

def match_category(title_text):
    """제목 기반 카테고리 분류 (제외 키워드 우선 체크)"""
    if not title_text: return None
    title_lower = title_text.lower()

    # 1. 제외 키워드 체크
    for ex_kw in KEYWORD_CATEGORIES.get(0, []):
        if ex_kw and ex_kw.strip().lower() in title_lower: return None

    # 2. 카테고리 매칭
    for cat_id, keywords in KEYWORD_CATEGORIES.items():
        if cat_id == 0: continue
        for kw in keywords:
            if kw and kw.strip().lower() in title_lower: return cat_id

    return None
