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
    0: "Delete/Ignore (단순 학사 행정, 졸업, 예비군, 수강신청, 시스템 점검 등 학생 모집과 무관한 공지)",

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
        "수강료", "준비사항", "필수사항"
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
SITES = [
    # === TYPE A (오전 9시 실행 그룹) ===
    {
        'type': 'A',
        'name': '공과대학',
        'code': 'IE',
        'url': 'https://engcollege.inha.ac.kr/engineering/9743/subview.do',
        'vendor_id': 1
    },
    {
        'type': 'A',
        'name': '기계공학과',
        'code': 'MEG',
        'url': 'https://mech.inha.ac.kr/mech/1823/subview.do',
        'vendor_id': 2
    },
    {
        'type': 'A',
        'name': '항공우주공학과',
        'code': 'ASE',
        'url': 'https://aerospace.inha.ac.kr/aerospace/9846/subview.do?enc=Zm5jdDF8QEB8JTJGYmJzJTJGYWVyb3NwYWNlJTJGMjQ4NSUyRmFydGNsTGlzdC5kbyUzRmJic0NsU2VxJTNEMTI4NyUyNmJic09wZW5XcmRTZXElM0QlMjZpc1ZpZXdNaW5lJTNEZmFsc2UlMjZzcmNoQ29sdW1uJTNEc2olMjZzcmNoV3JkJTNEJTI2',
        'vendor_id': 3
    },
    {
        'type': 'A',
        'name': '조선해양공학과',
        'code': 'NOE',
        'url': 'https://naoe.inha.ac.kr/naoe/1791/subview.do?enc=Zm5jdDF8QEB8JTJGYmJzJTJGbmFvZSUyRjQ3NyUyRmFydGNsTGlzdC5kbyUzRmJic0NsU2VxJTNEMzMxJTI2YmJzT3BlbldyZFNlcSUzRCUyNmlzVmlld01pbmUlM0RmYWxzZSUyNnNyY2hDb2x1bW4lM0RzaiUyNnNyY2hXcmQlM0QlMjY%3D',
        'vendor_id': 4
    },
    {
        'type': 'A',
        'name': '산업경영공학과',
        'code': 'IEN',
        'url': 'https://ie.inha.ac.kr/ie/963/subview.do',
        'vendor_id': 5
    },
    {
        'type': 'A',
        'name': '화학공학과',
        'code': 'CHE',
        'url': 'https://chemeng.inha.ac.kr/chemeng/2220/subview.do',
        'vendor_id': 6
    },
    {
        'type': 'A',
        'name': '고분자공학과',
        'code': 'PSE',
        'url': 'https://inhapoly.inha.ac.kr/inhapoly/2321/subview.do',
        'vendor_id': 7
    },
    {
        'type': 'A',
        'name': '신소재공학과',
        'code': 'MSE',
        'url': 'https://dmse.inha.ac.kr/dmse/2121/subview.do',
        'vendor_id': 8
    },
    {
        'type': 'A',
        'name': '사회인프라공학과',
        'code': 'CIV',
        'url': 'https://civil.inha.ac.kr/civil/2383/subview.do',
        'vendor_id': 9
    },

    {
        'type': 'A',
        'name': '환경공학과',
        'code': 'ENV',
        'url': 'https://environment.inha.ac.kr/environment/2541/subview.do',
        'vendor_id': 10
    },

    {
        'type': 'A',
        'name': '공간정보공학과',
        'code': 'GEO',
        'url': 'https://geoinfo.inha.ac.kr/geoinfo/2678/subview.do',
        'vendor_id': 11
    },

    {
        'type': 'A',
        'name': '건축학부',
        'code': 'ARC',
        'url': 'https://arch.inha.ac.kr/arch/2161/subview.do',
        'vendor_id': 12
    },
    {
        'type': 'A',
        'name': '에너지자원공학과',
        'code': 'ENR',
        'url': 'https://eneres.inha.ac.kr/eneres/3441/subview.do?enc=Zm5jdDF8QEB8JTJGYmJzJTJGZW5lcmVzJTJGODMwJTJGYXJ0Y2xMaXN0LmRvJTNGYmJzQ2xTZXElM0QyMDM2JTI2YmJzT3BlbldyZFNlcSUzRCUyNmlzVmlld01pbmUlM0RmYWxzZSUyNnNyY2hDb2x1bW4lM0RzaiUyNnNyY2hXcmQlM0QlMjY%3D',
        'vendor_id': 13
    },

    {
        'type': 'A',
        'name': '전기전자공학부',
        'code': 'EEC',
        'url': 'https://ee.inha.ac.kr/eee/16344/subview.do',
        'vendor_id': 14
    },

    {
        'type': 'A',
        'name': '반도체시스템공학과',
        'code': 'SSE',
        'url': 'https://sse.inha.ac.kr/sse/14301/subview.do',
        'vendor_id': 15
    },

    {
        'type': 'A',
        'name': '소프트웨어융합대학',
        'code': 'ITCU',
        'url': 'https://swcc.inha.ac.kr/act/2970/subview.do',
        'vendor_id': 16
    },

    {
        'type': 'A',
        'name': '소프트웨어융합대학',
        'code': 'ITCU',
        'url': 'https://swcc.inha.ac.kr/act/2971/subview.do',
        'vendor_id': 16
    },

    {
        'type': 'A',
        'name': '인공지능공학과',
        'code': 'AIEE',
        'url': 'https://doai.inha.ac.kr/doai/3046/subview.do',
        'vendor_id': 17
    },

    {
        'type': 'A',
        'name': '인공지능공학과',
        'code': 'AIEE',
        'url': 'https://doai.inha.ac.kr/doai/3047/subview.do',
        'vendor_id': 17
    },

    {
        'type': 'A',
        'name': '데이터사이언스학과',
        'code': 'DSC',
        'url': 'https://datascience.inha.ac.kr/datascience/3125/subview.do',
        'vendor_id': 18
    },

    {
        'type': 'A',
        'name': '데이터사이언스학과',
        'code': 'DSC',
        'url': 'https://datascience.inha.ac.kr/datascience/11588/subview.do',
        'vendor_id': 18
    },

    {
        'type': 'A',
        'name': '데이터사이언스학과',
        'code': 'DSC',
        'url': 'https://datascience.inha.ac.kr/datascience/3126/subview.do',
        'vendor_id': 18
    },
    {
        'type': 'A',
        'name': '스마트모빌리티공학',
        'code': 'SME',
        'url': 'https://sme.inha.ac.kr/sme/2867/subview.do',
        'vendor_id': 19
    },
    {
        'type': 'A',
        'name': '스마트모빌리티공학',
        'code': 'SME',
        'url': 'https://sme.inha.ac.kr/sme/2878/subview.do',
        'vendor_id': 19
    },

    {
        'type': 'A',
        'name': '디자인테크놀로지학과',
        'code': 'DET',
        'url': 'https://designtech.inha.ac.kr/designtech/3083/subview.do',
        'vendor_id': 20
    },

    {
        'type': 'A',
        'name': '컴퓨터공학과',
        'code': 'CSE',
        'url': 'https://cse.inha.ac.kr/cse/888/subview.do',
        'vendor_id': 21
    },

    {
        'type': 'A',
        'name': '컴퓨터공학과',
        'code': 'CSE',
        'url': 'https://cse.inha.ac.kr/cse/891/subview.do?enc=Zm5jdDF8QEB8JTJGYmJzJTJGY3NlJTJGMjQ0JTJGYXJ0Y2xMaXN0LmRvJTNGYmJzQ2xTZXElM0QxNDgzNjAlMjZiYnNPcGVuV3JkU2VxJTNEJTI2aXNWaWV3TWluZSUzRGZhbHNlJTI2c3JjaENvbHVtbiUzRHNqJTI2c3JjaFdyZCUzRCUyNg%3D%3D',
        'vendor_id': 21
    },

    {
        'type': 'A',
        'name': '산업경영공학과',
        'code': 'IEN',
        'url' : 'https://ie.inha.ac.kr/ie/979/subview.do?enc=Zm5jdDF8QEB8JTJGYmJzJTJGaWUlMkYyNzclMkZhcnRjbExpc3QuZG8lM0ZiYnNDbFNlcSUzRDE4ODglMjZiYnNPcGVuV3JkU2VxJTNEJTI2aXNWaWV3TWluZSUzRGZhbHNlJTI2c3JjaENvbHVtbiUzRHNqJTI2c3JjaFdyZCUzRCUyNg%3D%3D',
        'vendor_id': 5
    },

    {
        'type': 'A',
        'name': '소프트웨어중심대학사업단',
        'code': 'SWU',
        'url': 'https://swuniv.inha.ac.kr/swuniv/12703/subview.do',
        'vendor_id': 22
    },

    {
        'type': 'A',
        'name': '소프트웨어중심대학사업단',
        'code': 'SWU',
        'url': 'https://swuniv.inha.ac.kr/swuniv/15747/subview.do',
        'vendor_id': 22
    },

    {
        'type': 'A',
        'name': '이차전지융합학과',
        'code': 'IB',
        'url': 'https://ibattery.inha.ac.kr/ibattery/16267/subview.do',
        'vendor_id': 23
    },

    {
        'type': 'A',
        'name': '자연과학대학',
        'code': 'INS',
        'url': 'https://nscollege.inha.ac.kr/nscollege/3340/subview.do',
        'vendor_id': 24
    },

    {
        'type': 'A',
        'name': '수학과',
        'code': 'MTH',
        'url': 'https://math.inha.ac.kr/math/3528/subview.do',
        'vendor_id': 25
    },

    {
        'type': 'A',
        'name': '수학과',
        'code': 'MTH',
        'url': 'https://math.inha.ac.kr/math/3529/subview.do',
        'vendor_id': 25
    },

    {
        'type': 'A',
        'name': '통계학과',
        'code': 'STS',
        'url': 'https://statistics.inha.ac.kr/statistics/3383/subview.do',
        'vendor_id': 26
    },

    {
        'type': 'A',
        'name': '통계학과',
        'code': 'STS',
        'url': 'https://statistics.inha.ac.kr/statistics/3885/subview.do',
        'vendor_id': 26
    },

    {
        'type': 'A',
        'name': '통계학과',
        'code': 'STS',
        'url': 'https://statistics.inha.ac.kr/statistics/3402/subview.do',
        'vendor_id': 26
    },

    {
        'type': 'A',
        'name': '물리학과',
        'code': 'PHY',
        'url': 'https://physics.inha.ac.kr/physics/3908/subview.do',
        'vendor_id': 27
    },

    {
        'type': 'A',
        'name': '화학학과',
        'code': 'CHM',
        'url': 'https://chemistry.inha.ac.kr/chemistry/3297/subview.do',
        'vendor_id': 28
    },

    {
        'type': 'A',
        'name': '해양과학과',
        'code': 'OCN',
        'url': 'https://ocean.inha.ac.kr/ocean/17547/subview.do',
        'vendor_id': 29
    },

   {
        'type': 'A',
        'name': '해양과학과',
        'code': 'OCN',
        'url': 'https://ocean.inha.ac.kr/ocean/17548/subview.do',
        'vendor_id': 29
    },

    {
        'type': 'A',
        'name': '해양과학과',
        'code': 'OCN',
        'url': 'https://ocean.inha.ac.kr/ocean/17549/subview.do',
        'vendor_id': 29
    },

    {
        'type': 'A',
        'name': '해양과학과',
        'code': 'OCN',
        'url': 'https://ocean.inha.ac.kr/ocean/17550/subview.do',
        'vendor_id': 29
    },

    {
        'type': 'A',
        'name': '식품영양학과',
        'code': 'IFN',
        'url': 'https://foodnutri.inha.ac.kr/foodnutri/3555/subview.do',
        'vendor_id': 30
    },

    {
        'type': 'A',
        'name': '바이오시스템융합학부',
        'code': 'BIO',
        'url': 'https://biosyst.inha.ac.kr/biosyst/14989/subview.do',
        'vendor_id': 31
    },

    {
        'type': 'A',
        'name': '생명공학과',
        'code': 'IBE',
        'url': 'https://bio.inha.ac.kr/bio/2346/subview.do',
        'vendor_id': 32
    },

    {
        'type': 'A',
        'name': '생명공학과',
        'code': 'IBE',
        'url': 'https://bio.inha.ac.kr/bio/2347/subview.do',
        'vendor_id': 32
    },

    {
        'type': 'A',
        'name': '바이오제약공학과',
        'code': 'BPH',
        'url': 'https://biopharm.inha.ac.kr/biopharm/10309/subview.do',
        'vendor_id': 33
    },

    {
        'type': 'A',
        'name': '생명과학과',
        'code': 'IBG',
        'url': 'https://biology.inha.ac.kr/biology/3685/subview.do',
        'vendor_id': 34
    },

    {
        'type': 'A',
        'name': '생명과학과',
        'code': 'IBG',
        'url': 'https://biology.inha.ac.kr/biology/3689/subview.do',
        'vendor_id': 34
    },

    {
        'type': 'A',
        'name': '첨단바이오의약학과',
        'code': 'BMD',
        'url': 'https://biomedical.inha.ac.kr/biomedical/16160/subview.do',
        'vendor_id': 35
    },




    # ... A타입 사이트 30개 ...

    # === TYPE B (오전 12시 실행 그룹) ===
    {
        'type': 'B',
        'name': '이차전지공학(융합전공)',
        'code': 'IBF',
        'url': 'http://ibattery.website.ne.kr/sub/sub04_01.php',
        'vendor_id': 36
    },

    {
        'type': 'B',
        'name': '이차전지공학(융합전공)',
        'code': 'IBF',
        'url': 'http://ibattery.website.ne.kr/sub/sub04_02.php',
        'vendor_id': 36
    },



    # ... B타입 사이트 2개 ...

    # === TYPE C (오전 12시 실행 그룹) ===
    {
        'type': 'C',
        'name': '반도체공학(융합전공)',
        'code': 'SEF',
        'url': 'http://a221688b1.10pages.co.kr/board/list?bd_id=info01',
        'vendor_id': 37
    },



    # ... C타입 사이트 1개 ...

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
