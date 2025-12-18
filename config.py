import os
import pymysql.cursors

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

# 2. Gemini API KEY 로드
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', 'AIzaSyB8Px6izUcUh25SPwUsqtKrFmM6G2xE47A')

# 3. Gemini API 학습용 가이드
CATEGORY_GUIDE = {
    # [0: Exclude]
    0: "Delete/Ignore (단순 학사 행정, 졸업, 예비군, 수강신청, 시스템 점검 등 학생 모집과 무관한 공지)",

    # [1: Lecture] 학과/제도 설명회 추가
    1: "Lecture (특강, 세미나, 멘토링, 박람회, 기업 채용 설명회, 전공/학과 설명회, 현장실습 설명회)",

    # [2: Contest]
    2: "Contest (공모전, 챌린지 - 아이디어, 디자인, 영상 등 창작물을 제출하여 심사받는 형태)",

    # [3: Competition]
    3: "Competition (경진대회, 해커톤, 아이디어톤, 메이커톤 - 실시간/단기 경쟁 대회)",

    # [4: Activity] 범위를 '외부 활동/부트캠프'로 한정
    4: "Activity & Training (부트캠프, 대외활동, 서포터즈, 국비지원교육(KDT), 프로젝트 과정 및 이와 관련된 모집 설명회)",

    # [5: Scholarship]
    5: "Scholarship (장학금, 학자금 대출, 생활비 지원, 등록금 관련)"
}

# 4. 타겟 키워드
KEYWORD_CATEGORIES = {
    # [0: Exclude] 크롤링 단계에서 즉시 제외할 키워드
    0: [
        "강의진단", "강의평가", "졸업인증", "예비군", "점검", "졸업요건", "다학년프로젝트",
        "수강신청", "휴학", "복학", "전과", "예비군", "명예선서", "보고서"
    ],

    # [1: Lecture] 단순 청강, 정보 전달, 기업 설명회
    1: [
        "세미나", "설명회", "멘토링", "특강", "강의", "워크숍", "박람회",
        "GDG", "Google", "School", "Symposium",
        "LG", "SK", "하이닉스", "삼성", "Samsung", "AWS", "Microsoft", "Naver", "KT"
    ],

    # [2: Contest] 공모전
    2: [
        "공모전", "챌린지", "challenge"
    ],

    # [3: Competition] 대회
    3: [
        "경진", "대회", "해커톤", "hackerthon", "메이커톤", "makerthon",
        "아이디어톤", "ideathon", "콘테스트", "contest"
    ],

    # [4: Activity] 부트캠프, 대외활동, 봉사, 교류
    4: [
        "부트캠프", "bootcamp", "캠프", "camp", "서포터즈", "기자단", "봉사",
        "홍보대사", "동아리", "학회", "활동", "체험", "탐방",
        "프로젝트", "project", "훈련", "training", "내일배움카드", "KDT", "K-Digital Training", "국비"
    ],

    # [5: Scholarship] 장학
    5: [
        "장학", "장학생", "학자금", "등록금", "지원금", "생활비"
    ]
}

# 5. 사이트 목록 정의
SITES = [
    # === TYPE A (오전 9시 실행 그룹) ===
    {
        'type': 'A',
        'name': 'Inha_Engineering',
        'code': 'IE',
        'url': 'https://engcollege.inha.ac.kr/engineering/9743/subview.do',
        'vendor_id': 1
    },
    {
        'type': 'A',
        'name': 'Inha_Mech',
        'code': 'MEG',
        'url': 'https://mech.inha.ac.kr/mech/1823/subview.do',
        'vendor_id': 2
    },
    {
        'type': 'A',
        'name': 'Inha_AeroSpace',
        'code': 'ASE',
        'url': 'https://aerospace.inha.ac.kr/aerospace/9846/subview.do?enc=Zm5jdDF8QEB8JTJGYmJzJTJGYWVyb3NwYWNlJTJGMjQ4NSUyRmFydGNsTGlzdC5kbyUzRmJic0NsU2VxJTNEMTI4NyUyNmJic09wZW5XcmRTZXElM0QlMjZpc1ZpZXdNaW5lJTNEZmFsc2UlMjZzcmNoQ29sdW1uJTNEc2olMjZzcmNoV3JkJTNEJTI2',
        'vendor_id': 3
    },
    {
        'type': 'A',
        'name': 'Inha_ShipBuildingMarine',
        'code': 'NOE',
        'url': 'https://naoe.inha.ac.kr/naoe/1791/subview.do?enc=Zm5jdDF8QEB8JTJGYmJzJTJGbmFvZSUyRjQ3NyUyRmFydGNsTGlzdC5kbyUzRmJic0NsU2VxJTNEMzMxJTI2YmJzT3BlbldyZFNlcSUzRCUyNmlzVmlld01pbmUlM0RmYWxzZSUyNnNyY2hDb2x1bW4lM0RzaiUyNnNyY2hXcmQlM0QlMjY%3D',
        'vendor_id': 4
    },
    {
        'type': 'A',
        'name': 'Inha_IndustrialEngine',
        'code': 'IENA',
        'url': 'https://ie.inha.ac.kr/ie/963/subview.do',
        'vendor_id': 5
    },
    {
        'type': 'A',
        'name': 'Inha_ChemicalEngine',
        'code': 'CHE',
        'url': 'https://chemeng.inha.ac.kr/chemeng/2220/subview.do',
        'vendor_id': 6
    },
    {
        'type': 'A',
        'name': 'Inha_Polymer',
        'code': 'PSE',
        'url': 'https://inhapoly.inha.ac.kr/inhapoly/2321/subview.do',
        'vendor_id': 7
    },
    {
        'type': 'A',
        'name': 'Inha_Material',
        'code': 'MSE',
        'url': 'https://dmse.inha.ac.kr/dmse/2121/subview.do',
        'vendor_id': 8
    },
    {
        'type': 'A',
        'name': 'Inha_CivilInfra',
        'code': 'CIV',
        'url': 'https://civil.inha.ac.kr/civil/2383/subview.do',
        'vendor_id': 9
    },

    {
        'type': 'A',
        'name': 'Inha_Environment',
        'code': 'ENV',
        'url': 'https://environment.inha.ac.kr/environment/2541/subview.do',
        'vendor_id': 10
    },

    {
        'type': 'A',
        'name': 'Inha_GeoInfo',
        'code': 'GEO',
        'url': 'https://geoinfo.inha.ac.kr/geoinfo/2678/subview.do',
        'vendor_id': 11
    },

    {
        'type': 'A',
        'name': 'Inha_Arch',
        'code': 'ARC',
        'url': 'https://arch.inha.ac.kr/arch/2161/subview.do',
        'vendor_id': 12
    },
    {
        'type': 'A',
        'name': 'Inha_Energy',
        'code': 'ENR',
        'url': 'https://eneres.inha.ac.kr/eneres/3441/subview.do?enc=Zm5jdDF8QEB8JTJGYmJzJTJGZW5lcmVzJTJGODMwJTJGYXJ0Y2xMaXN0LmRvJTNGYmJzQ2xTZXElM0QyMDM2JTI2YmJzT3BlbldyZFNlcSUzRCUyNmlzVmlld01pbmUlM0RmYWxzZSUyNnNyY2hDb2x1bW4lM0RzaiUyNnNyY2hXcmQlM0QlMjY%3D',
        'vendor_id': 13
    },

    {
        'type': 'A',
        'name': 'Inha_electronic',
        'code': 'EEC',
        'url': 'https://ee.inha.ac.kr/eee/16344/subview.do',
        'vendor_id': 14
    },

    {
        'type': 'A',
        'name': 'Inha_SSE',
        'code': 'SSE',
        'url': 'https://sse.inha.ac.kr/sse/14301/subview.do',
        'vendor_id': 15
    },

    {
        'type': 'A',
        'name': 'Inha_Swcc_Announcement',
        'code': 'ITCA',
        'url': 'https://swcc.inha.ac.kr/act/2970/subview.do',
        'vendor_id': 16
    },

    {
        'type': 'A',
        'name': 'Inha_Swcc_Uni_Announcement',
        'code': 'ITCU',
        'url': 'https://swcc.inha.ac.kr/act/2971/subview.do',
        'vendor_id': 16
    },

    {
        'type': 'A',
        'name': 'Inha_Ai_Announcement',
        'code': 'AIEA',
        'url': 'https://doai.inha.ac.kr/doai/3046/subview.do',
        'vendor_id': 17
    },

    {
        'type': 'A',
        'name': 'Inha_Ai_Event',
        'code': 'AIEE',
        'url': 'https://doai.inha.ac.kr/doai/3047/subview.do',
        'vendor_id': 17
    },

    {
        'type': 'A',
        'name': 'Inha_DataScience_Announcement',
        'code': 'DSCA',
        'url': 'https://datascience.inha.ac.kr/datascience/3125/subview.do',
        'vendor_id': 18
    },

    {
        'type': 'A',
        'name': 'Inha_DataScience_Contest',
        'code': 'DSCC',
        'url': 'https://datascience.inha.ac.kr/datascience/11588/subview.do',
        'vendor_id': 18
    },

    {
        'type': 'A',
        'name': 'Inha_DataScience_Event',
        'code': 'DSCE',
        'url': 'https://datascience.inha.ac.kr/datascience/3126/subview.do',
        'vendor_id': 18
    },
    {
        'type': 'A',
        'name': 'Inha_SmartMobile_Announcement',
        'code': 'SMEA',
        'url': 'https://sme.inha.ac.kr/sme/2867/subview.do',
        'vendor_id': 19
    },
    {
        'type': 'A',
        'name': 'Inha_SmartMobile_Event',
        'code': 'SMEE',
        'url': 'https://sme.inha.ac.kr/sme/2878/subview.do',
        'vendor_id': 19
    },

    {
        'type': 'A',
        'name': 'Inha_DesignTech',
        'code': 'DET',
        'url': 'https://designtech.inha.ac.kr/designtech/3083/subview.do',
        'vendor_id': 20
    },

    {
        'type': 'A',
        'name': 'Inha_CSE_Announcement',
        'code': 'CSEA',
        'url': 'https://cse.inha.ac.kr/cse/888/subview.do',
        'vendor_id': 21
    },

    {
        'type': 'A',
        'name': 'Inha_CSE_Contest',
        'code': 'CSEC',
        'url': 'https://cse.inha.ac.kr/cse/891/subview.do?enc=Zm5jdDF8QEB8JTJGYmJzJTJGY3NlJTJGMjQ0JTJGYXJ0Y2xMaXN0LmRvJTNGYmJzQ2xTZXElM0QxNDgzNjAlMjZiYnNPcGVuV3JkU2VxJTNEJTI2aXNWaWV3TWluZSUzRGZhbHNlJTI2c3JjaENvbHVtbiUzRHNqJTI2c3JjaFdyZCUzRCUyNg%3D%3D',
        'vendor_id': 21
    },

    {
        'type': 'A',
        'name': 'Inha_IndustrialEngine_Event',
        'code': 'IENE',
        'url' : 'https://ie.inha.ac.kr/ie/979/subview.do?enc=Zm5jdDF8QEB8JTJGYmJzJTJGaWUlMkYyNzclMkZhcnRjbExpc3QuZG8lM0ZiYnNDbFNlcSUzRDE4ODglMjZiYnNPcGVuV3JkU2VxJTNEJTI2aXNWaWV3TWluZSUzRGZhbHNlJTI2c3JjaENvbHVtbiUzRHNqJTI2c3JjaFdyZCUzRCUyNg%3D%3D',
        'vendor_id': 5
    },

    {
        'type': 'A',
        'name': 'Inha_swuniv_Announcement',
        'code': 'SWUA',
        'url': 'https://swuniv.inha.ac.kr/swuniv/12703/subview.do',
        'vendor_id': 22
    },

    {
        'type': 'A',
        'name': 'Inha_swuniv_Event',
        'code': 'SWUE',
        'url': 'https://swuniv.inha.ac.kr/swuniv/15747/subview.do',
        'vendor_id': 22
    },



    # ... A타입 사이트 30개 ...

    # === TYPE B (오전 12시 실행 그룹) ===
    {
        'type': 'B',
        'name': 'Inha_Ibattery_Announcement',
        'code': 'IBA',
        'url': 'http://ibattery.website.ne.kr/sub/sub04_01.php',
        'vendor_id': 23
    },

    {
        'type': 'B',
        'name': 'Inha_Ibattery_Event',
        'code': 'IBE',
        'url': 'http://ibattery.website.ne.kr/sub/sub04_02.php',
        'vendor_id': 23
    },



    # ... B타입 사이트 2개 ...

    # === TYPE C (오전 12시 실행 그룹) ===
    {
        'type': 'C',
        'name': 'Inha_FVT',
        'code': 'FVT',
        'url': 'http://fvt.inha.ac.kr/fvt/board/5',
        'vendor_id': 24
    },



    # ... C타입 사이트 1개 ...

    # === TYPE D (오전 12시 실행 그룹) ===
    {
        'type': 'D',
        'name': 'Inha_SE',
        'code': 'SEE',
        'url': 'http://a221688b1.10pages.co.kr/board/list?bd_id=info01',
        'vendor_id': 25
    },



    # ... D타입 사이트 1개 ...

    # === TYPE E (오전 12시 실행 그룹) ===
    {
        'type': 'E',
        'name': 'Inha_JOB',
        'code': 'JOB',
        'url': 'https://job.inha.ac.kr/Community/Program/ProgramList.aspx',
        'vendor_id': 26
    }



    # ... E타입 사이트 2개 ...
]

# 6. 크롤링 결과 JSON으로 저장
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_ROOT = os.path.join(BASE_DIR, 'data')

HISTORY_DIR = os.path.join(DATA_ROOT, 'history')
QUEUE_DIR = os.path.join(DATA_ROOT, 'queue')

# 폴더가 없으면 미리 생성
for d in [HISTORY_DIR, QUEUE_DIR]:
    if not os.path.exists(d):
        os.makedirs(d)
        print(f"📁 폴더 생성 완료: {d}")