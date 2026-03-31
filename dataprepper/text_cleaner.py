import re
import html


class Cleaner:
    """게시글 본문 텍스트 정제"""

    def __init__(self):
        # [1] 제거할 가비지 패턴 (HTML 엔티티 정규식 제거)
        self.garbage = [
            r' ',
            r'<script.*?>.*?</script>',
            r'<style.*?>.*?</style>',
            r'\r',
        ]

        # [2] 목록 기호 패턴 (이 기호로 시작하면 절대 앞줄과 합치지 않음)
        self.list_pattern = re.compile(r'^(\d+[\.\)]|[가-하][\.\)]|[-※*▶■□○●]|\(\d+\)|\([가-하]\)|\[\d+\]|\[[가-하]\])')

        # [3] 문장 종결 패턴 (이 기호로 끝나면 정상적인 문장의 끝으로 간주)
        self.end_pattern = re.compile(r'([.?!:]|[다요음함임기])$')

    def clean_title_text(self, text):
        """게시글 제목 텍스트 정제 (말머리 및 뱃지 통합 제거)"""
        if not text: return ""

        # [1] HTML 엔티티 복원 및 기본 공백 정제
        text = html.unescape(text)
        text = text.replace('\xa0', ' ').replace('\u200b', '').replace('\t', ' ').replace('\n', ' ').replace('\r', ' ')
        text = re.sub(r' {2,}', ' ', text).strip()
        base_text = text

        # [2] 제목 맨 앞의 말머리 패턴 제거
        text = re.sub(r'^(?:\[[^\]]*\]\s*)+', '', text)

        # [3] 불필요한 뱃지/키워드([새글], (NEW), N 등) 통합 제거
        badge_pattern = r'\[(?:새글|NEW|N)\]|\((?:새글|NEW|N)\)|(?:새글|NEW|N)\b'
        text = re.sub(badge_pattern, '', text, flags=re.IGNORECASE)

        # [4] 연속된 공백 압축 및 최종 정리
        text = re.sub(r' {2,}', ' ', text).strip()

        # [5] 정제한 결과가 너무 짧으면(2자 미만) 정제 전 텍스트(base_text) 롤백
        if len(text) < 2:
            return base_text
            
        return text

    def normalize_for_similarity(self, text):
        """유사도 분석을 위한 더욱 정밀한 정규화"""
        if not text: return ""
        # [1] 접속사 및 구분자 공백 치환
        text = text.replace('_', ' ').replace('및', ' ').replace(',', ' ')
        # [2] 한자 제거
        text = re.sub(r'[\u4e00-\u9fff]+', '', text)
        # [3] 괄호 및 특수문자 제거
        text = re.sub(r'[\(\)\[\]\{\}\-\~\~]', ' ', text)
        # [4] 날짜/시간 패턴 소거
        text = re.sub(r'\d+월\s?\d+일?|\d+\.\d+|\d+/\d+|(?:오전|오후)\s?\d+시?|\d+일까지', ' ', text)
        # [5] 연도 표준화
        text = re.sub(r'(\d{4})학년도|(\d{4})년', r'\1', text)
        return re.sub(r' {2,}', ' ', text).strip()

    def clean_html_to_text(self, html_content):
        """HTML 본문을 텍스트로 변환하며 테이블을 [ 본 문 참 고 ]로 치환함"""
        if not html_content: return ""

        # [1] 테이블 치환
        html_content = re.sub(r'<table.*?>.*?</table>', '\n[ 본 문 참 고 ]\n', html_content, flags=re.DOTALL | re.IGNORECASE)

        # [2] 개행 관련 태그 치환
        html_content = re.sub(r'<br\s*/?>', '\n', html_content, flags=re.IGNORECASE)
        html_content = re.sub(r'</(p|div|li|tr)>', '\n', html_content, flags=re.IGNORECASE)

        # [3] 나머지 모든 태그 제거 및 일반 텍스트 정제 호출
        text = re.sub(r'<[^>]+>', ' ', html_content)
        return self.clean_contents_text(text)

    def clean_contents_text(self, text):
        """단일 텍스트 정제"""
        if not text: return ""

        # [1] HTML 엔티티 복원 및 투명 공백 제거
        text = html.unescape(text)
        text = text.replace('\xa0', ' ').replace('\u200b', '').replace('\t', ' ')

        # [2] 가비지 태그(<p>, <br> 등) 제거
        for p in self.garbage:
            text = re.sub(p, ' ', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<[^>]+>', '', text)

        # [3] 연속된 스페이스바 공백 1개로 압축
        text = re.sub(r' {2,}', ' ', text)

        # [4] 끊어진 줄 병합
        lines = [line.strip() for line in text.split('\n')]
        cleaned_lines = []

        for line in lines:
            if not line:
                cleaned_lines.append("")
                continue

            if cleaned_lines and cleaned_lines[-1] != "":
                prev_line = cleaned_lines[-1]

                if not self.end_pattern.search(prev_line) and not self.list_pattern.match(line):
                    cleaned_lines[-1] = prev_line + " " + line
                    continue

            cleaned_lines.append(line)

        # [5] 과도한 빈 줄 2개로 압축
        final_text = '\n'.join(cleaned_lines)
        final_text = re.sub(r'\n{3,}', '\n\n', final_text)

        return final_text.strip()

    def clean_contents(self, articles):
        """리스트 내 모든 본문 정제"""
        if not articles: return articles
        for a in articles:
            if 'content' in a:
                a['content'] = self.clean_contents_text(a['content'])
        return articles