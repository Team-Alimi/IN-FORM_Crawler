import os
import pymysql.cursors

# 1. 프로젝트 경로 지정
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_ROOT = os.path.join(BASE_DIR, 'data')
LOG_DIR = os.path.join(BASE_DIR, 'log')
HISTORY_DIR = os.path.join(DATA_ROOT, 'history')
QUEUE_DIR = os.path.join(DATA_ROOT, 'queue')

# 1. 데이터베이스 설정
DB_CONFIG = {
    'host': os.getenv('DB_HOST', '127.0.0.1'),
    'port': int(os.getenv('DB_PORT', 13306)),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD', ''),
    'db': os.getenv('DB_NAME', 'informserver'),
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor
}

# 2. User-Agent Header
BASE_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
BOT_INFO = "informBot/1.0 (+https://github.com/Team-Alimi; team.alimi.inform@gmail.com)"
FINAL_USER_AGENT = f"{BASE_USER_AGENT} {BOT_INFO}"

COMMON_HEADERS = {
    "User-Agent": FINAL_USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Upgrade-Insecure-Requests": "1"
}

# 3. UPSTAGE API KEY 로드
UPSTAGE_AI_API_KEY = os.getenv('UPSTAGE_AI_API_KEY', '')

# 4. UPSTAGE AI API 학습용 가이드
CATEGORY_GUIDE = {
    # [0: Exclude]
    0: "Delete/Ignore (단순 학사 행정, 졸업, 예비군, 수강신청, 시스템 점검, 안전 교육 등 학생 진로 설계와 무관한 공지)",

    # [1: Contest/Competition]
    1: "Contest (공모전, 챌린지 - 아이디어, 디자인, 영상 등 창작물을 제출하여 심사받는 형태), Competition (경진대회, 해커톤, 아이디어톤, 메이커톤 - 실시간/단기 경쟁 대회)",

    # [2: Lecture]
    2: "Lecture (특강, 세미나, 멘토링, 박람회, 기업 채용 설명회, 전공/학과 설명회, 현장실습 설명회)",

    # [3: Activity]
    3: "Activity & Training (부트캠프, 대외활동, 서포터즈, 국비지원교육(KDT), 견학 프로그램, 기업 탐방, 프로젝트 과정 및 이와 관련된 모집 설명회)",

    # [4: Scholarship]
    4: "Scholarship (장학금, 학자금 대출, 생활비 지원, 등록금 관련)"
}

# 4. 타겟 키워드
KEYWORD_CATEGORIES = {
    # [0: Exclude] 크롤링 단계에서 즉시 제외할 키워드
    0: [
        "강의진단", "강의평가", "졸업인증", "예비군", "점검", "졸업요건", "다학년프로젝트",
        "수강신청", "휴학", "복학", "전과", "예비군", "명예선서", "보고서", "설문조사",
        "비교표", "도입", "줌", "주소", "오픈채팅방", "전공 모집", "보안서약서", "질문", "답변",
        "수강료", "준비사항", "필수사항", "안전교육", "전공상담", "등록유형별"
    ],

    # [1: Contest/Competition] 공모전/대회
    1: [
        "공모전", "챌린지", "challenge",
        "경진", "대회", "해커톤", "hackerthon", "메이커톤", "makerthon",
        "아이디어톤", "ideathon", "콘테스트", "contest"
    ],

    # [2: Lecture] 단순 청강, 정보 전달, 기업 설명회
    2: [
        "세미나", "설명회", "멘토링", "특강", "강의", "워크숍", "박람회",
        "GDG", "Google", "School", "Symposium",
        "LG", "SK", "하이닉스", "삼성", "Samsung", "AWS", "Microsoft", "Naver", "KT"
    ],

    # [3: Activity] 부트캠프, 대외활동, 봉사, 교류
    3: [
        "부트캠프", "bootcamp", "캠프", "camp", "서포터즈", "기자단", "봉사",
        "홍보대사", "동아리", "학회", "활동", "체험", "탐방",
        "프로젝트", "project", "훈련", "training", "내일배움카드", "KDT", "K-Digital Training", "국비"
    ],

    # [4: Scholarship] 장학
    4: [
        "장학", "장학생", "학자금", "등록금", "지원금", "생활비"
    ]
}

# 5. 사이트 목록 정의
def _load_all_sites():
    from glob import glob
    import json

    all_sites = []
    seeds_dir = os.path.join(DATA_ROOT, 'seeds')
    json_paths = glob(os.path.join(seeds_dir, 'type_*.json'))
    
    for path in json_paths:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                all_sites.extend(json.load(f))
        except Exception as e:
            from common.logger import log_status
            log_status("Config", f"사이트 로딩 실패 ({path}): {e}", "WARN")
            
    return all_sites

SITES = _load_all_sites()

# 6. 크롤링 결과 JSON으로 저장
for d in [HISTORY_DIR, QUEUE_DIR, LOG_DIR]:
    if not os.path.exists(d):
        os.makedirs(d)
        from common.logger import log_status
        log_status("System", f"폴더 생성 완료: {d}", "SAVE")
