class DateExtractionRules:
    """AI를 사용한 게시글 내 날짜 추출(Extraction)을 위한 규칙과 프롬프트를 정의함"""

    @staticmethod
    def get_prompt(base_date):
        """날짜 추출 작업을 위한 시스템 프롬프트 반환"""
        return f"""
        [TASK 2: Date Extraction]
        You are an expert data extractor. Extract 'start_date' and 'due_date' from the given text based on the Reference Date: {base_date} and the Category classified in TASK 1.
        Return the result ONLY in valid YYYY-MM-DD (ISO 8601) format, or null.
        
        <Extraction Logic (CRITICAL)>
        TASK 1에서 분류된 카테고리(Category ID)에 따라 추출해야 하는 날짜의 기준이 다릅니다:
        
        - 대상 A: Category 1 (CONTEST), 3 (SCHOLAR), 4 (ACTIVITY)
          👉 타겟: 신청/접수/제출 기간 (Application Period)
        - 대상 B: Category 2 (LECTURE)
          👉 타겟: 실제 행사 기간 (Event Period)
        
        <Advanced Reasoning & Distractor Rejection (CRITICAL)>
        복잡하고 불친절한 텍스트에서 엉뚱한 날짜를 추출하지 않도록 아래 규칙을 엄수하세요:
        
        1. 방해 요소(Distractors) 필터링:
           - '신청 기간'을 찾을 때(대상 A): "교육 기간", "O.T(오리엔테이션)", "결과 발표일", "서류평가일" 등의 날짜는 함정이므로 절대 추출하지 마세요. 오직 "제출", "접수", "신청", "마감" 키워드에 연결된 날짜만 찾으세요. (예: "제출 기한: ~3.15" -> due=3.15)
           - '행사 기간'을 찾을 때(대상 B): "신청 마감일", "사전 접수" 등을 무시하고 실제 본 행사가 열리는 날짜만 찾으세요.
        
        2. 시작일(start_date)이 생략된 엣지 케이스 처리 (매우 중요):
           - 텍스트에 시작일 없이 마감일/제출기한(예: "~ 3.15(금) 오후 1시까지")만 명시되어 있다면, due_date는 해당 마감일로 설정하고 **start_date는 크롤링 기준일인 Reference Date ({base_date})로 설정**하세요. 억지로 다른 일정(교육일, 발표일 등)을 시작일로 끼워 맞추지 마세요.
        
        3. 날짜 추론 및 포맷팅 변환:
           - "2024.3.15", "3/15", "3월 15일" -> 2024-03-15 형태로 변환.
           - 연도가 생략된 경우 Reference Date ({base_date})의 연도를 따릅니다.
           - "자정", "오늘 밤" -> 당일 날짜 / "주말 지나고" -> 다가오는 월요일.
           - 구체적인 시점을 알 수 없는 "상시 모집", "추후 공지", "채용 시 마감" 등은 start_date와 due_date 모두 null 반환.
        """
