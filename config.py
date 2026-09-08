import os

POSTGRES_SECRET_FIELDS = ("host", "port", "dbname", "username", "password")


class DatabaseSecretConfigurationError(ValueError):
    """Raised when the configured database secret cannot satisfy the crawler contract."""


class DatabaseConnectionRetryableError(ConnectionError):
    """Signals a database authentication or connection failure eligible for one refresh."""


def _create_secrets_manager_client(service_name):
    if service_name != "secretsmanager":
        raise DatabaseSecretConfigurationError("unsupported secrets service")

    try:
        import boto3
    except ImportError as error:
        raise DatabaseSecretConfigurationError(
            "boto3 is required for database secret resolution"
        ) from error

    return boto3.client(service_name)


def resolve_postgres_database_secret(secret_id, client_factory=None):
    """Read and validate the approved PostgreSQL connection payload without logging it."""
    if not isinstance(secret_id, str) or not secret_id.strip():
        raise DatabaseSecretConfigurationError("database secret identifier is required")

    client_factory = client_factory or _create_secrets_manager_client
    response = client_factory("secretsmanager").get_secret_value(SecretId=secret_id)
    secret_string = response.get("SecretString")
    if not isinstance(secret_string, str):
        raise DatabaseSecretConfigurationError(
            "database secret must contain SecretString"
        )

    try:
        import json

        payload = json.loads(secret_string)
    except (TypeError, ValueError) as error:
        raise DatabaseSecretConfigurationError(
            "database secret is not valid JSON"
        ) from error

    if not isinstance(payload, dict) or set(payload) != set(POSTGRES_SECRET_FIELDS):
        raise DatabaseSecretConfigurationError(
            "database secret fields do not match the approved contract"
        )

    return {field: payload[field] for field in POSTGRES_SECRET_FIELDS}


def connect_with_one_secret_refresh(secret_id, client_factory, connect):
    """Retry one database authentication/connection failure after a secret refresh."""
    credentials = resolve_postgres_database_secret(secret_id, client_factory)
    try:
        return connect(credentials)
    except DatabaseConnectionRetryableError:
        refreshed_credentials = resolve_postgres_database_secret(
            secret_id, client_factory
        )
        return connect(refreshed_credentials)


# 1. 프로젝트 경로 지정
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_ROOT = os.path.join(BASE_DIR, "data")


def _runtime_directory(environment_name, default_path):
    """Use a deployment-provided local directory or the safe repository default."""
    configured_path = os.getenv(environment_name)
    if not configured_path or not configured_path.strip():
        return default_path
    return os.path.abspath(os.path.expanduser(configured_path.strip()))


LOG_DIR = _runtime_directory("CRAWLER_LOG_DIR", os.path.join(BASE_DIR, "log"))
HISTORY_DIR = _runtime_directory(
    "CRAWLER_HISTORY_DIR", os.path.join(DATA_ROOT, "history")
)
QUEUE_DIR = _runtime_directory("CRAWLER_QUEUE_DIR", os.path.join(DATA_ROOT, "queue"))

# 2. User-Agent Header
BASE_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
BOT_INFO = "informBot/1.0 (+https://github.com/Team-Alimi; team.alimi.inform@gmail.com)"
FINAL_USER_AGENT = f"{BASE_USER_AGENT} {BOT_INFO}"

COMMON_HEADERS = {
    "User-Agent": FINAL_USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Upgrade-Insecure-Requests": "1",
}

# 3. UPSTAGE API KEY 로드
UPSTAGE_API_KEY = os.getenv("UPSTAGE_API_KEY", "")

# 4. v11/V14 AI category contract
CANONICAL_CATEGORY_CODES = (
    "ACADEMIC",
    "ACTIVITY",
    "CAREER",
    "CERTIFICATION",
    "CONTEST",
    "EVENT",
    "FOREIGN",
    "LECTURE",
    "RESEARCH",
    "SCHOLARSHIP",
    "VOLUNTEER",
    "ETC",
)


def normalize_category_code(value):
    if not isinstance(value, str):
        raise ValueError("AI category_code must be a canonical string")

    category_code = value.strip().upper()
    if category_code not in CANONICAL_CATEGORY_CODES:
        raise ValueError("AI category_code is not in the v11/V14 contract")

    return category_code


def category_code_allows_write(value):
    """Return whether a valid v11/V14 category can enter the crawler write path."""
    normalize_category_code(value)
    return True


CATEGORY_GUIDE = {
    "ACADEMIC": "학사",
    "ACTIVITY": "대외활동",
    "CAREER": "취업·인턴십",
    "CERTIFICATION": "자격증",
    "CONTEST": "공모전·대회",
    "EVENT": "행사·축제",
    "FOREIGN": "어학",
    "LECTURE": "특강·세미나",
    "RESEARCH": "학술·연구",
    "SCHOLARSHIP": "장학",
    "VOLUNTEER": "봉사",
    "ETC": "기타·미분류",
}

# 4. 타겟 키워드
KEYWORD_CATEGORIES = {
    # [0: Exclude] 크롤링 단계에서 즉시 제외할 키워드
    0: [
        "강의진단",
        "강의평가",
        "졸업인증",
        "예비군",
        "점검",
        "졸업요건",
        "다학년프로젝트",
        "수강신청",
        "휴학",
        "복학",
        "전과",
        "예비군",
        "명예선서",
        "보고서",
        "설문조사",
        "비교표",
        "도입",
        "줌",
        "주소",
        "오픈채팅방",
        "전공 모집",
        "보안서약서",
        "질문",
        "답변",
        "수강료",
        "준비사항",
        "필수사항",
        "안전교육",
        "전공상담",
        "등록유형별",
    ],
    # [1: Contest/Competition] 공모전/대회
    1: [
        "공모전",
        "챌린지",
        "challenge",
        "경진",
        "대회",
        "해커톤",
        "hackerthon",
        "메이커톤",
        "makerthon",
        "아이디어톤",
        "ideathon",
        "콘테스트",
        "contest",
    ],
    # [2: Lecture] 단순 청강, 정보 전달, 기업 설명회
    2: [
        "세미나",
        "설명회",
        "멘토링",
        "특강",
        "강의",
        "워크숍",
        "박람회",
        "GDG",
        "Google",
        "School",
        "Symposium",
        "LG",
        "SK",
        "하이닉스",
        "삼성",
        "Samsung",
        "AWS",
        "Microsoft",
        "Naver",
        "KT",
    ],
    # [3: Activity] 부트캠프, 대외활동, 봉사, 교류
    3: [
        "부트캠프",
        "bootcamp",
        "캠프",
        "camp",
        "서포터즈",
        "기자단",
        "봉사",
        "홍보대사",
        "동아리",
        "학회",
        "활동",
        "체험",
        "탐방",
        "프로젝트",
        "project",
        "훈련",
        "training",
        "내일배움카드",
        "KDT",
        "K-Digital Training",
        "국비",
    ],
    # [4: Scholarship] 장학
    4: ["장학", "장학생", "학자금", "등록금", "지원금", "생활비"],
}


# 5. 타입별 사이트 목록 로드 함수
def load_sites(typ):
    """지정된 타입의 시드 파일만 타겟팅하여 로드함"""
    import json

    from common.logger import log_status

    seeds_dir = os.path.join(DATA_ROOT, "seeds")
    path = os.path.join(seeds_dir, f"type_{typ.lower()}.json")

    if not os.path.exists(path):
        log_status("Config", f"시드 파일 없음: {path}", "WARN")
        return []

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log_status("Config", f"사이트 로딩 실패 ({path}): {e}", "WARN")
        return []


# 6. 크롤링 결과 저장 폴더 생성
for d in [HISTORY_DIR, QUEUE_DIR, LOG_DIR]:
    os.makedirs(d, exist_ok=True)
