import os
import logging
from logging.handlers import TimedRotatingFileHandler

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

    log_dir = "/opt/project/log"
    os.makedirs(log_dir, exist_ok=True)

    file_path = os.path.join(log_dir, f"crawler_{crawler_type}.log")
    file_handler = TimedRotatingFileHandler(
        filename=file_path,
        when='midnight',
        interval=1,
        backupCount=30,
        encoding='utf-8'
    )
    file_handler.suffix = "%Y-%m-%d"
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