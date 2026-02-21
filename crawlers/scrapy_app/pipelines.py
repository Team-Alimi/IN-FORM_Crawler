from scrapy.exceptions import DropItem
from config import KEYWORD_CATEGORIES


class CategoryPipeline:
    """
    수집된 아이템의 제목을 기반으로 카테고리를 분류하고,
    제외 키워드가 포함된 경우 드롭하는 파이프라인.
    """
    def process_item(self, item, spider):
        title_text = item.get('title', '')
        if not title_text:
            raise DropItem(f"제목 없음으로 제외: {item.get('original_url')}")

        title_lower = title_text.lower()

        # 1. 제외 키워드 체크 (Category 0)
        exclude_keywords = KEYWORD_CATEGORIES.get(0, [])
        for ex_kw in exclude_keywords:
            if ex_kw and ex_kw.strip() and ex_kw.lower() in title_lower:
                raise DropItem(f"제외 키워드 포함: {ex_kw}")

        # 2. 카테고리 매칭
        matched_cat_id = None
        for cat_id, keywords in KEYWORD_CATEGORIES.items():
            if cat_id == 0: continue
            for kw in keywords:
                if kw and kw.strip() and kw.lower() in title_lower:
                    matched_cat_id = cat_id
                    break
            if matched_cat_id: break

        # 3. 결과 처리
        if matched_cat_id:
            item['category_id'] = matched_cat_id
            return item
        else:
            # 카테고리가 매칭되지 않는 글은 정보 전달 가치가 낮다고 판단하여 제외
            raise DropItem(f"카테고리 매칭 실패: {title_text}")

class CleanupPipeline:
    """
    데이터 필드 정제 및 최종 검증을 담당하는 파이프라인.
    텍스트가 없더라도 첨부파일(사진)이 있으면 수집을 허용함.
    """
    def process_item(self, item, spider):
        # 본문 내 불필요한 공백/줄바꿈 최종 정리
        if item.get('content'):
            item['content'] = item['content'].strip()
        
        # 필수 필드 누락 체크 (content는 attachments가 있는 경우 생략 가능)
        required_fields = ['unique_id', 'title', 'original_url']
        for field in required_fields:
            if not item.get(field):
                raise DropItem(f"필수 필드 누락 ({field}): {item.get('original_url')}")
        
        # 텍스트와 첨부파일 둘 다 없는 경우 제외
        if not item.get('content') and not item.get('attachments'):
             raise DropItem(f"내용(텍스트/이미지)이 전혀 없음: {item.get('original_url')}")
        
        return item
