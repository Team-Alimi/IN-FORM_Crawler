from datetime import datetime
from dateutil.relativedelta import relativedelta

def get_limit_date():
    """n개월 전 1일 날짜 반환 (시간 00:00:00)"""
    now = datetime.now()
    limit = now - relativedelta(months=2)
    return limit.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

def parse_date_raw(date_text):
    if not date_text: return None
    date_text = date_text.strip()

    formats = [
        '%Y.%m.%d',  # Type A
        '%Y-%m-%d',  # Type B
        '%Y.%m.%d %H:%M',  # Type C
        '%Y/%m/%d'
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(date_text, fmt)
            return dt.replace(hour=0, minute=0, second=0, microsecond=0)
        except ValueError:
            continue
    return None

def format_date_str(date_obj):
    if date_obj is None: return None
    return date_obj.strftime("%Y-%m-%d")
