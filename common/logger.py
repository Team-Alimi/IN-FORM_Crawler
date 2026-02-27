import os
import time
import logging
from datetime import datetime

from config import LOG_DIR

_logger = None


def init_logger(crawler_type="default"):
    """
    크롤러 시작 시 단 한 번 호출하여 파일 저장 경로와 로거를 세팅합니다.
    """
    global _logger
    if _logger is not None:
        return _logger

    _logger = logging.getLogger(f"INFORM_Crawler_{crawler_type}")
    _logger.setLevel(logging.INFO)

    formatter = logging.Formatter('[%(asctime)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

    type_log_dir = os.path.join(LOG_DIR, crawler_type)
    if not os.path.exists(type_log_dir):
        os.makedirs(type_log_dir, exist_ok=True)

    now = time.time()
    for f in os.listdir(type_log_dir):
        f_path = os.path.join(type_log_dir, f)
        if os.path.isfile(f_path) and f.endswith(".log"):
            if os.stat(f_path).st_mtime < now - 30 * 86400:
                try:
                    os.remove(f_path)
                except Exception:
                    pass

    # 로그 파일명 Type+YY+MM+DD+HH+MM+SS.log (예: A260228012402.log)
    current_time = datetime.now().strftime("%y%m%d%H%M%S")
    file_name = f"{crawler_type}{current_time}.log"
    file_path = os.path.join(type_log_dir, file_name)

    file_handler = logging.FileHandler(file_path, encoding='utf-8')
    file_handler.setFormatter(formatter)
    _logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    _logger.addHandler(console_handler)

    return _logger


def get_status_icon(level="INFO"):
    """로그 레벨에 따른 아이콘 반환"""
    icons = {
        "START": "🚀",
        "SUCCESS": "✅",
        "WARN": "⚠️",
        "ERROR": "❌",
        "STOP": "🛑",
        "COLLECT": "✨",
        "SAVE": "💾",
        "INFO": "📄",
        "LINK": "🔗",
        "PHASE": "⚙️",
        "DONE": "🎉"
    }
    return icons.get(level.upper(), "📄")


def log_status(site_name, message, level="INFO"):
    """표준화된 로그 출력 형식"""
    global _logger
    if _logger is None:
        init_logger()

    icon = get_status_icon(level)
    formatted_message = f"{icon} [{site_name}] {message}"

    upper_level = level.upper()
    if upper_level in ["ERROR", "STOP"]:
        _logger.error(formatted_message)
    elif upper_level == "WARN":
        _logger.warning(formatted_message)
    else:
        _logger.info(formatted_message)