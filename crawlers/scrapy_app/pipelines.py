from scrapy.exceptions import DropItem
from config import KEYWORD_CATEGORIES


class CategoryPipeline:
    def process_item(self, item, spider):
        # title 가져오기
        title_text = item.get('title', '')
        if not title_text:
            raise DropItem(f"제목 없음으로 제외: {item.get('url')}")

        title_lower = title_text.lower()

        # 제외 키워드 체크
        exclude_keywords = KEYWORD_CATEGORIES.get(0, [])
        for ex_kw in exclude_keywords:
            if ex_kw and ex_kw.strip() and ex_kw.lower() in title_lower:
                raise DropItem(f"제외 키워드 포함: {ex_kw}")

        # 카테고리 매칭
        matched_cat_id = None
        for cat_id, keywords in KEYWORD_CATEGORIES.items():
            if cat_id == 0: continue
            for kw in keywords:
                if kw and kw.strip() and kw.lower() in title_lower:
                    matched_cat_id = cat_id
                    break
            if matched_cat_id: break

        if matched_cat_id:
            item['category_id'] = matched_cat_id
            return item
        else:
            raise DropItem(f"카테고리 매칭 실패: {title_text}")