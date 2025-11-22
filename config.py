import os

# 1. 데이터베이스 설정
DB_CONFIG = {
    'host': 'localhost',
    'user': 'your_user',
    'password': 'your_password',
    'db': 'your_db_name',
    'charset': 'utf8mb4',
    'cursorclass': 'pymysql.cursors.DictCursor'
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
        'name': 'Inha_IndustrialManage',
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
        'name': 'Inha_Swcc_Announcement',
        'url': 'https://swcc.inha.ac.kr/act/2970/subview.do',
        'vendor_id': 15
    },

    {
        'type': 'A',
        'name': 'Inha_Swcc_Uni_Announcement',
        'url': 'https://swcc.inha.ac.kr/act/2971/subview.do',
        'vendor_id': 15
    },

    {
        'type': 'A',
        'name': 'Inha_Ai_Announcement',
        'url': 'https://doai.inha.ac.kr/doai/3046/subview.do',
        'vendor_id': 16
    },

    {
        'type': 'A',
        'name': 'Inha_Ai_Event',
        'url': 'https://doai.inha.ac.kr/doai/3047/subview.do',
        'vendor_id': 16
    },

    {
        'type': 'A',
        'name': 'Inha_DataScience_Announcement',
        'url': 'https://datascience.inha.ac.kr/datascience/3125/subview.do',
        'vendor_id': 17
    },

    {
        'type': 'A',
        'name': 'Inha_DataScience_Contest',
        'url': 'https://datascience.inha.ac.kr/datascience/11588/subview.do',
        'vendor_id': 17
    },

    {
        'type': 'A',
        'name': 'Inha_DataScience_Event',
        'url': 'https://datascience.inha.ac.kr/datascience/3126/subview.do',
        'vendor_id': 17
    },
    {
        'type': 'A',
        'name': 'Inha_SmartMobile_Announcement',
        'url': 'https://sme.inha.ac.kr/sme/2867/subview.do',
        'vendor_id': 18
    },
    {
        'type': 'A',
        'name': 'Inha_SmartMobile_Event',
        'url': 'https://sme.inha.ac.kr/sme/2878/subview.do',
        'vendor_id': 18
    },

    {
        'type': 'A',
        'name': 'Inha_DesignTech',
        'url': 'https://designtech.inha.ac.kr/designtech/3083/subview.do',
        'vendor_id': 19
    },

    {
        'type': 'A',
        'name': 'Inha_CSE_Announcement',
        'url': 'https://cse.inha.ac.kr/cse/888/subview.do',
        'vendor_id': 20
    },

    {
        'type': 'A',
        'name': 'Inha_CSE_Contest',
        'url': 'https://cse.inha.ac.kr/cse/891/subview.do?enc=Zm5jdDF8QEB8JTJGYmJzJTJGY3NlJTJGMjQ0JTJGYXJ0Y2xMaXN0LmRvJTNGYmJzQ2xTZXElM0QxNDgzNjAlMjZiYnNPcGVuV3JkU2VxJTNEJTI2aXNWaWV3TWluZSUzRGZhbHNlJTI2c3JjaENvbHVtbiUzRHNqJTI2c3JjaFdyZCUzRCUyNg%3D%3D',
        'vendor_id': 20
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