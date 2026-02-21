import re

class Cleaner:
    """게시글 본문 텍스트 정제"""

    def __init__(self):
        self.garbage = [
            r'<!--.*?-->', r'<script.*?>.*?</script>',
            r'<style.*?>.*?</style>', r'&[a-z0-9#]+;', r'\r',
        ]

    def clean_contents_text(self, text):
        """단일 텍스트 정제"""
        if not text: return ""
        for p in self.garbage:
            text = re.sub(p, ' ', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return '\n'.join([l.strip() for l in text.split('\n')]).strip()

    def clean_contents(self, articles):
        """리스트 내 모든 본문 정제"""
        if not articles: return articles
        for a in articles:
            if 'content' in a:
                a['content'] = self.clean_contents_text(a['content'])
        return articles
