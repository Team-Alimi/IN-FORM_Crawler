import os
import pymysql.cursors

# 1. 데이터베이스 설정
DB_CONFIG = {
    'host': 'localhost',
    'user': 'your_user',
    'password': 'your_password',
    'db': 'your_db_name',
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor
}

# 2. 타겟 키워드
KEYWORD_CATEGORIES = {
    1: [ #LECTURE
        "세미나", "설명회", "멘토링", "특강", "강의"
    ],
    2: [ #CONTEST
        "공모전", "챌린지", "challenge", "프로젝트", "project"
    ],
    3: [ #COMPETITION
        "대회", "해커톤", "hackerthon", "메이커톤", "makerthon", "아이디어톤", "ideathon", "콘테스트", "contest"
    ]
}

# 3. 사이트 목록 정의
# vendor_id: DB의 vendors 테이블에 존재하는 ID여야 합니다. (FK 제약조건)
SITES = [
    # === TYPE A (오전 9시 실행 그룹) ===
    {
        'type': 'A',
        'name': 'Inha_SSE',
        'url': 'https://sse.inha.ac.kr/sse/14301/subview.do',
        'vendor_id': 1
    },
    {
        'type': 'A',
        'name': 'Inha_Mech',
        'url': 'https://mech.inha.ac.kr/mech/1823/subview.do',
        'vendor_id': 2
    },

    # ... A타입 사이트 30개 ...

    # === TYPE B (오전 12시 실행 그룹) ===
    {
        'type': 'B',
        'name': 'Inha_FutureVehicleTech',
        'url': 'https://fvt.inha.ac.kr/fvt/board/5',
        'vendor_id': 21
    },
]

# 4. 크롤링 결과 JSON으로 저장
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'crawled_data')

# 폴더가 없으면 미리 생성
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)