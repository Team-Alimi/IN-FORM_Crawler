from config import CATEGORY_GUIDE

class ClassificationRules:
    """AI를 사용한 게시글 분류(Classification)를 위한 규칙과 프롬프트를 정의함"""

    @staticmethod
    def get_prompt():
        """분류 작업을 위한 프롬프트 반환"""
        category_desc = "\n".join([f"{k}. {v}" for k, v in CATEGORY_GUIDE.items()])

        return f"""
        [TASK 1: Classification]
        You are an expert text classifier. Classify the given text into the single most appropriate Category ID (1 to 4) based on the following definitions:
        {category_desc}

        <Critical Rules>
        1. Context Priority: 분류 시 '본문(Content)'보다 '제목(Title)'의 핵심 키워드와 맥락을 최우선으로 분석하세요.
        2. Strict Mapping: 오직 하나의 가장 적합한 Category ID만 정수로 도출해야 합니다.
        
        <Disambiguation (CRITICAL RULES)>
        1. 공모전 및 경진대회 (Challenge & Competition):
           - '아이디어 공모전', 'UCC/수기 공모전' 등 기획/창작 행사부터 '해커톤(Hackathon)', '경진대회', '프로그래밍 대회' 등 실무/개발 중심의 대회까지 모두 Category 1 (CONTEST)로 분류하세요.
        
        2. 특강, 설명회, 박람회 (Lecture, Briefing & Expo):
           - 일반적인 직무/취업 특강, 학교 제도 안내, 전공/학과 간담회, '박람회(Fair)', '엑스포(Expo)' 등 단순 정보 제공성 행사는 Category 2 (LECTURE)로 분류하세요.
           - 단, 부트캠프/대외활동/서포터즈 모집을 '안내'하기 위한 설명회는 모집 성격이 강하므로 Category 4 (ACTIVITY)로 분류하세요.
        
        3. 장학 및 금전적 지원 (Financial Aid):
           - '장학금', '학업 장려금', '생활비 지원' 등 현금성/등록금 지원 프로그램은 무조건 Category 3 (SCHOLAR)로 분류하세요.
        
        4. 대내외 활동 및 장기 교육 프로그램 (Activity, Project & Training):
           - KDT(국비지원), SSAFY(싸피), 크래프톤 정글, 우아한테크코스 등 집중 교육/부트캠프는 Category 4 (ACTIVITY)로 분류하세요.
           - 서포터즈, 멘토링, 외부 프로젝트 팀 모집 등도 Category 4 (ACTIVITY)로 분류하세요.
        
        5. 외부 기업 탐방 및 현장 체험 (Company Tour & Field Experience):
           - '마이크로소프트 견학 프로그램', 'OO기업 현장체험/탐방' 등 대학 외부의 기업이나 기관을 직접 방문하여 견학하거나 체험하는 프로그램은 예외 없이 Category 4 (ACTIVITY)로 분류하세요.
        """
