from config import CATEGORY_GUIDE


class ClassificationRules:
    """AI를 사용한 게시글 분류(Classification)를 위한 규칙과 프롬프트를 정의함"""

    @staticmethod
    def get_prompt():
        """분류 작업을 위한 프롬프트 반환"""
        category_desc = "\n".join([f"{k}. {v}" for k, v in CATEGORY_GUIDE.items()])

        return f"""
        [TASK 1: Classification]
        You are an expert text classifier. Classify the given text into exactly one canonical category_code based on the following definitions:
        {category_desc}

        <Critical Rules>
        1. Context Priority: 분류 시 '본문(Content)'보다 '제목(Title)'의 핵심 키워드와 맥락을 최우선으로 분석하세요.
        2. Strict Mapping: 숫자 ID나 legacy label이 아닌 위 canonical category_code 하나만 도출해야 합니다.
        3. 어느 canonical category에도 명확히 맞지 않으면 ETC를 사용합니다. ETC는 유효한
           crawler category_code이며, category_code를 생략하거나 legacy EXCLUDE를 반환하면 안 됩니다.
        """
