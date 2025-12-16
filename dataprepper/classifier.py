import google.generativeai as genai
import time
from config import GEMINI_API_KEY, CATEGORY_GUIDE


class AIClassifier:
    def __init__(self):
        if not GEMINI_API_KEY:
            print("⚠️ [AI] GEMINI_API_KEY가 설정되지 않았습니다. AI 분류를 건너뜁니다.")
            self.model = None
            return

        # 1. Gemini 설정
        genai.configure(api_key=GEMINI_API_KEY)

        self.model = genai.GenerativeModel('gemini-2.5-flash')

        # 2. 프롬프트 구성 (카테고리 정보 주입)
        self.category_desc = "\n".join([f"{k}. {v}" for k, v in CATEGORY_GUIDE.items()])

        self.base_prompt = f"""
                You are an expert AI assistant for a university student developer community.
                Your task is to classify university announcements into specific categories based on the provided guide.

                [Category Definitions]
                {self.category_desc}

                [Instruction Rules]
                1. **Analyze Context**: Title has higher priority than Content.
                2. **Strict Mapping**: Map the content to the most appropriate Category ID.
                3. **Disambiguation (CRITICAL RULES)**:
                   - **'Briefing/Session' Classification (Important)**: 
                     - **Classify as 1 (Lecture)**: If it is about **School System, Major/Department(전공/학과), Field Practice(현장실습), Career Fair**, or General Job Briefing.
                     - **Classify as 4 (Activity)**: ONLY if the briefing is specifically for a **Bootcamp, KDT(Digital Training), Supporters, or External Project Team**.
                   - **'Fair' & 'Expo'**: Always **1 (Lecture)**.
                   - **'Project' & 'Training'**: KDT, SSAFY, Jungle, Academy -> **4 (Activity)**.
                   - **'Challenge' vs 'Competition'**: "Challenge/Contest" -> 2, "Hackathon/Competition" -> 3.
                   - **Financial Aid**: -> **5 (Scholarship)**.

                [Examples]
                - "2025 Field Practice Semester Briefing" -> 1 (School System -> Lecture)
                - "Battery Engineering Major Briefing" -> 1 (Major Info -> Lecture)
                - "2026 Krafton Jungle Integrated Briefing" -> 4 (Bootcamp -> Activity)
                - "Future Auto Career Design Fair" -> 1
                - "Winter AI Coding Boot Camp" -> 4
                - "Tuition Support Program" -> 5
                """

    def predict(self, title, content):
        """제목과 본문을 받아 카테고리 ID(int)를 반환"""
        if not self.model: return None

        # 본문이 너무 길면 앞부분 1000자만 사용 (비용/속도 절약)
        summary_content = content[:1000].strip() if content else "No Content"

        user_input = f"""
        [Input Data]
        Title: {title}
        Content: {summary_content}

        Answer:
        """

        try:
            # AI 호출
            response = self.model.generate_content(self.base_prompt + user_input)
            result_text = response.text.strip()

            # 숫자만 추출 (가끔 "Category 1" 이렇게 답할 수 있으므로)
            import re
            numbers = re.findall(r'\d+', result_text)

            if numbers:
                cat_id = int(numbers[0])
                if cat_id in CATEGORY_GUIDE:
                    return cat_id

            return None  # 분류 실패

        except Exception as e:
            print(f"   ⚠️ AI 호출 실패: {e}")
            return None

    def classify_batch(self, article_list):
        """리스트를 받아 AI 분류 후 업데이트 (Rate Limit 고려)"""
        if not self.model: return article_list

        print(f"   🤖 [AI] 신규 데이터 {len(article_list)}건 분류 시작 (Gemini 2.5 Flash)...")

        count = 0
        for article in article_list:
            # 이미 키워드로 분류된 것도 AI로 재검증하고 싶다면 조건 제거
            # 여기서는 '키워드 매칭 실패(None)'인 경우만 AI 사용 (비용 절약)
            # 혹은 정확도를 위해 전체 다 돌릴 수도 있음. (현재는 전체 다 돌리는 로직)

            # AI 예측
            ai_id = self.predict(article['title'], article['content'])

            if ai_id:
                # 기존 키워드 매칭보다 AI를 우선할지, 보완할지 결정
                # 여기서는 AI가 분류에 성공했으면 덮어쓰기
                article['category_id'] = ai_id
                # print(f"      💡 AI 분류: {ai_id} -> {article['title'][:15]}...")

            count += 1

            # [중요] Free Tier Rate Limit 방지 (15 RPM -> 4초에 1회)
            # 안전하게 4초 대기 (하루 1500회 제한 안에서 안전)
            time.sleep(4)

            if count % 5 == 0:
                print(f"      ... {count}건 처리 중")

        return article_list