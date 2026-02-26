import os
import json
import pymysql
import builtins
from config import DB_CONFIG, QUEUE_DIR


def inject_json_to_db():
    """
    지정된 사이트들의 JSON 파일을 읽어서 DB에 Bulk Insert 수행
    """
    conn = pymysql.connect(**DB_CONFIG)

    try:
        with conn.cursor() as cursor:
            # 통합 INSERT 처리
            insert_path = os.path.join(QUEUE_DIR, "INSERT_DATA.json")
            if os.path.exists(insert_path):
                print(f"📥 통합 데이터(INSERT) 업로드 시작...")
                with open(insert_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                if data:
                    for item in data:
                        # 1. school_articles 테이블에 삽입
                        sql_article = """
                            INSERT INTO school_articles
                                (title, content, start_date, due_date, created_at, updated_at, category_id)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """
                        cursor.execute(sql_article, (
                            item.get('title'),
                            item.get('content'),
                            item.get('start_date'),
                            item.get('due_date'),
                            item.get('created_at'),
                            item.get('updated_at'),
                            item.get('category_id')
                        ))
                        article_id = cursor.lastrowid

                        # 2. school_article_vendors 맵핑 테이블에 삽입
                        vendor_urls = item.get('vendor_urls', {})
                        if not vendor_urls and item.get('vendor_id'):
                            # 만약 vendor_urls가 비어있고 단일 vendor_id만 있다면 보정
                            vendor_urls = {str(item['vendor_id']): item.get('original_url')}

                        if vendor_urls:
                            sql_mapping = """
                                INSERT INTO school_article_vendors
                                    (article_id, vendor_id, original_url)
                                VALUES (%s, %s, %s)
                            """
                            mapping_values = [
                                (article_id, int(v_id), url)
                                for v_id, url in vendor_urls.items()
                            ]
                            cursor.executemany(sql_mapping, mapping_values)

                    conn.commit()
                    print(f"   ✅ {len(data)}건 Insert 및 맵핑 완료.")
                    os.remove(insert_path)

            # 통합 UPDATE 처리
            update_path = os.path.join(QUEUE_DIR, "UPDATE_DATA.json")
            if os.path.exists(update_path):
                print(f"🔄 통합 데이터(UPDATE) 처리 시작...")
                with open(update_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                if data:
                    for item in data:
                        # URL을 기준으로 article_id 찾기 (가장 최근 등록된 매핑 기준)
                        # 실제로는 original_url이 유니크하지 않을 수 있으므로 주의
                        find_id_sql = "SELECT article_id FROM school_article_vendors WHERE original_url = %s LIMIT 1"
                        cursor.execute(find_id_sql, (item['original_url'],))
                        res = cursor.fetchone()
                        
                        if res:
                            article_id = res['article_id']
                            
                            # 1. 본문 내용 업데이트
                            sql_update_art = """
                                UPDATE school_articles
                                SET title = %s, content = %s, updated_at = %s, category_id = %s
                                WHERE article_id = %s
                            """
                            cursor.execute(sql_update_art, (
                                item['title'], item['content'], item['updated_at'], 
                                item.get('category_id'), article_id
                            ))

                            # 2. 맵핑 정보 갱신 (이미 있는 vendor_id면 무시, 없으면 추가)
                            vendor_urls = item.get('vendor_urls', {})
                            for v_id, url in vendor_urls.items():
                                sql_check = "SELECT id FROM school_article_vendors WHERE article_id = %s AND vendor_id = %s"
                                cursor.execute(sql_check, (article_id, int(v_id)))
                                if not cursor.fetchone():
                                    sql_ins_map = "INSERT INTO school_article_vendors (article_id, vendor_id, original_url) VALUES (%s, %s, %s)"
                                    cursor.execute(sql_ins_map, (article_id, int(v_id), url))

                    conn.commit()
                    print(f"   ✅ {len(data)}건 Update 완료.")
                    os.remove(update_path)

    except Exception as e:
        builtins.print(f"❌ DB 업로드 중 치명적 오류: {e}")
    finally:
        conn.close()
