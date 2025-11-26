import os
import pymysql.cursors

# 1. 데이터베이스 설정
DB_CONFIG = {
    'host': '172.16.0.4',
    'port': 13306,
    'user': 'root',
    'password': '',
    'db': 'informserver',
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor
}

# 2. 타겟 키워드
KEYWORD_CATEGORIES = {
    0: [ #EXCLUDE
        "강의진단", "강의평가", "졸업인증"
    ],
    1: [ #LECTURE
        "세미나", "설명회", "멘토링", "특강", "강의", "워크숍"
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
        'name': 'Inha_Engineering',
        'url': 'https://engcollege.inha.ac.kr/engineering/9743/subview.do',
        'vendor_id': 1
    },
    {
        'type': 'A',
        'name': 'Inha_Mech',
        'url': 'https://mech.inha.ac.kr/mech/1823/subview.do',
        'vendor_id': 2
    },
    {
        'type': 'A',
        'name': 'Inha_AeroSpace',
        'url': 'https://aerospace.inha.ac.kr/aerospace/9846/subview.do?enc=Zm5jdDF8QEB8JTJGYmJzJTJGYWVyb3NwYWNlJTJGMjQ4NSUyRmFydGNsTGlzdC5kbyUzRmJic0NsU2VxJTNEMTI4NyUyNmJic09wZW5XcmRTZXElM0QlMjZpc1ZpZXdNaW5lJTNEZmFsc2UlMjZzcmNoQ29sdW1uJTNEc2olMjZzcmNoV3JkJTNEJTI2',
        'vendor_id': 3
    },
    {
        'type': 'A',
        'name': 'Inha_ShipBuildingMarine',
        'url': 'https://naoe.inha.ac.kr/naoe/1791/subview.do?enc=Zm5jdDF8QEB8JTJGYmJzJTJGbmFvZSUyRjQ3NyUyRmFydGNsTGlzdC5kbyUzRmJic0NsU2VxJTNEMzMxJTI2YmJzT3BlbldyZFNlcSUzRCUyNmlzVmlld01pbmUlM0RmYWxzZSUyNnNyY2hDb2x1bW4lM0RzaiUyNnNyY2hXcmQlM0QlMjY%3D',
        'vendor_id': 4
    },
    {
        'type': 'A',
        'name': 'Inha_IndustrialEngine',
        'url': 'https://ie.inha.ac.kr/ie/963/subview.do',
        'vendor_id': 5
    },
    {
        'type': 'A',
        'name': 'Inha_ChemicalEngine',
        'url': 'https://chemeng.inha.ac.kr/chemeng/2220/subview.do',
        'vendor_id': 6
    },
    {
        'type': 'A',
        'name': 'Inha_Polymer',
        'url': 'https://inhapoly.inha.ac.kr/inhapoly/2321/subview.do',
        'vendor_id': 7
    },
    {
        'type': 'A',
        'name': 'Inha_Material',
        'url': 'https://dmse.inha.ac.kr/dmse/2121/subview.do',
        'vendor_id': 8
    },
    {
        'type': 'A',
        'name': 'Inha_CivilInfra',
        'url': 'https://civil.inha.ac.kr/civil/2383/subview.do',
        'vendor_id': 9
    },

    {
        'type': 'A',
        'name': 'Inha_Environment',
        'url': 'https://environment.inha.ac.kr/environment/2541/subview.do',
        'vendor_id': 10
    },

    {
        'type': 'A',
        'name': 'Inha_GeoInfo',
        'url': 'https://geoinfo.inha.ac.kr/geoinfo/2678/subview.do',
        'vendor_id': 11
    },

    {
        'type': 'A',
        'name': 'Inha_Arch',
        'url': 'https://arch.inha.ac.kr/arch/2161/subview.do',
        'vendor_id': 12
    },
    {
        'type': 'A',
        'name': 'Inha_Energy',
        'url': 'https://eneres.inha.ac.kr/eneres/3441/subview.do?enc=Zm5jdDF8QEB8JTJGYmJzJTJGZW5lcmVzJTJGODMwJTJGYXJ0Y2xMaXN0LmRvJTNGYmJzQ2xTZXElM0QyMDM2JTI2YmJzT3BlbldyZFNlcSUzRCUyNmlzVmlld01pbmUlM0RmYWxzZSUyNnNyY2hDb2x1bW4lM0RzaiUyNnNyY2hXcmQlM0QlMjY%3D',
        'vendor_id': 13
    },

    {
        'type': 'A',
        'name': 'Inha_electronic',
        'url': 'https://ee.inha.ac.kr/eee/16344/subview.do',
        'vendor_id': 14
    },

    {
        'type': 'A',
        'name': 'Inha_SSE',
        'url': 'https://sse.inha.ac.kr/sse/14301/subview.do',
        'vendor_id': 15
    },

    {
        'type': 'A',
        'name': 'Inha_Swcc_Announcement',
        'url': 'https://swcc.inha.ac.kr/act/2970/subview.do',
        'vendor_id': 16
    },

    {
        'type': 'A',
        'name': 'Inha_Swcc_Uni_Announcement',
        'url': 'https://swcc.inha.ac.kr/act/2971/subview.do',
        'vendor_id': 16
    },

    {
        'type': 'A',
        'name': 'Inha_Ai_Announcement',
        'url': 'https://doai.inha.ac.kr/doai/3046/subview.do',
        'vendor_id': 17
    },

    {
        'type': 'A',
        'name': 'Inha_Ai_Event',
        'url': 'https://doai.inha.ac.kr/doai/3047/subview.do',
        'vendor_id': 17
    },

    {
        'type': 'A',
        'name': 'Inha_DataScience_Announcement',
        'url': 'https://datascience.inha.ac.kr/datascience/3125/subview.do',
        'vendor_id': 18
    },

    {
        'type': 'A',
        'name': 'Inha_DataScience_Contest',
        'url': 'https://datascience.inha.ac.kr/datascience/11588/subview.do',
        'vendor_id': 18
    },

    {
        'type': 'A',
        'name': 'Inha_DataScience_Event',
        'url': 'https://datascience.inha.ac.kr/datascience/3126/subview.do',
        'vendor_id': 18
    },
    {
        'type': 'A',
        'name': 'Inha_SmartMobile_Announcement',
        'url': 'https://sme.inha.ac.kr/sme/2867/subview.do',
        'vendor_id': 19
    },
    {
        'type': 'A',
        'name': 'Inha_SmartMobile_Event',
        'url': 'https://sme.inha.ac.kr/sme/2878/subview.do',
        'vendor_id': 19
    },

    {
        'type': 'A',
        'name': 'Inha_DesignTech',
        'url': 'https://designtech.inha.ac.kr/designtech/3083/subview.do',
        'vendor_id': 20
    },

    {
        'type': 'A',
        'name': 'Inha_CSE_Announcement',
        'url': 'https://cse.inha.ac.kr/cse/888/subview.do',
        'vendor_id': 21
    },

    {
        'type': 'A',
        'name': 'Inha_CSE_Contest',
        'url': 'https://cse.inha.ac.kr/cse/891/subview.do?enc=Zm5jdDF8QEB8JTJGYmJzJTJGY3NlJTJGMjQ0JTJGYXJ0Y2xMaXN0LmRvJTNGYmJzQ2xTZXElM0QxNDgzNjAlMjZiYnNPcGVuV3JkU2VxJTNEJTI2aXNWaWV3TWluZSUzRGZhbHNlJTI2c3JjaENvbHVtbiUzRHNqJTI2c3JjaFdyZCUzRCUyNg%3D%3D',
        'vendor_id': 21
    },

    {
        'type': 'A',
        'name': 'Inha_IndustrialEngine_Event',
        'url' : 'https://ie.inha.ac.kr/ie/979/subview.do?enc=Zm5jdDF8QEB8JTJGYmJzJTJGaWUlMkYyNzclMkZhcnRjbExpc3QuZG8lM0ZiYnNDbFNlcSUzRDE4ODglMjZiYnNPcGVuV3JkU2VxJTNEJTI2aXNWaWV3TWluZSUzRGZhbHNlJTI2c3JjaENvbHVtbiUzRHNqJTI2c3JjaFdyZCUzRCUyNg%3D%3D',
        'vendor_id': 5
    },

    {
        'type': 'A',
        'name': 'Inha_swuniv_Announcement',
        'url': 'https://swuniv.inha.ac.kr/swuniv/12703/subview.do',
        'vendor_id': 22
    },

    {
        'type': 'A',
        'name': 'Inha_swuniv_Event',
        'url': 'https://swuniv.inha.ac.kr/swuniv/15747/subview.do',
        'vendor_id': 22
    },



    # ... A타입 사이트 30개 ...

    # === TYPE B (오전 12시 실행 그룹) ===
    {
        'type': 'B',
        'name': 'Inha_Ibattery_Announcement',
        'url': 'http://ibattery.website.ne.kr/sub/sub04_01.php',
        'vendor_id': 23
    },

    {
        'type': 'B',
        'name': 'Inha_Ibattery_Event',
        'url': 'http://ibattery.website.ne.kr/sub/sub04_02.php',
        'vendor_id': 23
    },



    # ... B타입 사이트 2개 ...

    # === TYPE C (오전 12시 실행 그룹) ===
    {
        'type': 'C',
        'name': 'Inha_FVT',
        'url': 'https://fvt.inha.ac.kr/fvt/board/5',
        'vendor_id': 24
    },



    # ... C타입 사이트 1개 ...

    # === TYPE D (오전 12시 실행 그룹) ===
    {
        'type': 'D',
        'name': 'Inha_SE',
        'url': 'http://a221688b1.10pages.co.kr/board/list?bd_id=info01',
        'vendor_id': 25
    },



    # ... D타입 사이트 1개 ...

    # === TYPE E (오전 12시 실행 그룹) ===
    {
        'type': 'E',
        'name': 'Inha_JOB',
        'url': 'https://job.inha.ac.kr/Community/Program/ProgramList.aspx',
        'vendor_id': 26
    }



    # ... E타입 사이트 2개 ...
]

# 4. 크롤링 결과 JSON으로 저장
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'crawled_data')

# 폴더가 없으면 미리 생성
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)