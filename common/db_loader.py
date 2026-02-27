import os
import json
import pymysql
import glob
from config import DB_CONFIG, QUEUE_DIR
from common.logger import log_status


def _execute_load(cursor, data, mode="INSERT"):
    """실제 DB에 데이터를 삽입/업데이트하는 내부 로직"""
    if not data:
        return

    for article in data:
        if mode == "INSERT":
            # [1] school_articles 테이블에 삽입
            sql_article = """
                INSERT INTO school_articles
                    (title, content, start_date, due_date, created_at, updated_at, category_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(sql_article, (
                article.get('title'),
                article.get('content'),
                article.get('start_date'),
                article.get('due_date'),
                article.get('created_at'),
                article.get('updated_at'),
                article.get('category_id')
            ))
            article_id = cursor.lastrowid

            # [2] school_article_vendors 맵핑 테이블에 삽입
            vendor_ids = article.get('vendor_ids', [])
            vendor_urls = article.get('vendor_urls', [])
            if vendor_ids and vendor_urls:
                sql_mapping = "INSERT INTO school_article_vendors (article_id, vendor_id, original_url) VALUES (%s, %s, %s)"
                mapping_values = [(article_id, int(v_id), url) for v_id, url in zip(vendor_ids, vendor_urls)]
                cursor.executemany(sql_mapping, mapping_values)

            # [3] attachments 테이블에 삽입
            attachments = article.get('attachments', [])
            if attachments:
                sql_attachment = "INSERT INTO attachments (attachment_url, article_id, article_type) VALUES (%s, %s, %s)"
                attachment_values = [(att.get('attachment_url'), article_id, 'SCHOOL') for att in attachments if att.get('attachment_url')]
                if attachment_values:
                    cursor.executemany(sql_attachment, attachment_values)

        elif mode == "UPDATE":
            # URL을 기준으로 article_id 찾기
            find_id_sql = "SELECT article_id FROM school_article_vendors WHERE original_url = %s LIMIT 1"
            cursor.execute(find_id_sql, (article['original_url'],))
            res = cursor.fetchone()
            
            if res:
                article_id = res['article_id']
                # [1] school_articles 업데이트
                sql_update_art = """
                    UPDATE school_articles
                    SET title = %s, content = %s, updated_at = %s, category_id = %s,
                        start_date = %s, due_date = %s
                    WHERE article_id = %s
                """
                cursor.execute(sql_update_art, (
                    article['title'], article['content'], article['updated_at'], 
                    article.get('category_id'), article.get('start_date'), 
                    article.get('due_date'), article_id
                ))

                # [2] 맵핑 정보 갱신
                vendor_ids = article.get('vendor_ids', [])
                vendor_urls = article.get('vendor_urls', [])
                for v_id, url in zip(vendor_ids, vendor_urls):
                    sql_check = "SELECT id FROM school_article_vendors WHERE article_id = %s AND vendor_id = %s"
                    cursor.execute(sql_check, (article_id, int(v_id)))
                    if not cursor.fetchone():
                        sql_ins_map = "INSERT INTO school_article_vendors (article_id, vendor_id, original_url) VALUES (%s, %s, %s)"
                        cursor.execute(sql_ins_map, (article_id, int(v_id), url))
                
                # [3] 첨부파일 갱신
                attachments = article.get('attachments', [])
                for att in attachments:
                    url = att.get('attachment_url')
                    if url:
                        sql_check_att = "SELECT id FROM attachments WHERE article_id = %s AND attachment_url = %s"
                        cursor.execute(sql_check_att, (article_id, url))
                        if not cursor.fetchone():
                            sql_ins_att = "INSERT INTO attachments (attachment_url, article_id, article_type) VALUES (%s, %s, %s)"
                            cursor.execute(sql_ins_att, (url, article_id, 'SCHOOL'))


def load_json_to_db():
    """
    queue 디렉토리의 모든 INSERT_DATA*.json, UPDATE_DATA*.json 파일을 DB에 적재하고 삭제합니다.
    """
    conn = pymysql.connect(**DB_CONFIG)

    try:
        with conn.cursor() as cursor:
            # 1. INSERT 파일 처리
            insert_files = glob.glob(os.path.join(QUEUE_DIR, "INSERT_DATA*.json"))
            for path in insert_files:
                file_name = os.path.basename(path)
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if data:
                    _execute_load(cursor, data, mode="INSERT")
                    log_status("DBLoader", f"{file_name}: {len(data)}건 Insert 완료", "SUCCESS")
                os.remove(path)

            # 2. UPDATE 파일 처리
            update_files = glob.glob(os.path.join(QUEUE_DIR, "UPDATE_DATA*.json"))
            for path in update_files:
                file_name = os.path.basename(path)
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if data:
                    _execute_load(cursor, data, mode="UPDATE")
                    log_status("DBLoader", f"{file_name}: {len(data)}건 Update 완료", "SUCCESS")
                os.remove(path)

            conn.commit()

    except Exception as e:
        log_status("DBLoader", f"DB 적재 중 오류 발생: {e}", "ERROR")
        conn.rollback()
    finally:
        conn.close()


if __name__ == "__main__":
    load_json_to_db()
