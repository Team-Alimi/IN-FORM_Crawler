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
    icon = get_status_icon(level)
    print(f"{icon} [{site_name}] {message}")
