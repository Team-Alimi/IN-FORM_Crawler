import os
import json
import pymysql
import builtins
from config import DB_CONFIG, QUEUE_DIR


def inject_json_to_db():
    """
    지정된 사이트들의 JSON 파일을 읽어서 DB에 Bulk Insert 수행
    target_sites: main.py에서 넘겨준 사이트 정보 리스트
    """
    # 1. DB 연결 (한 번만 연결해서 재사용)
    conn = pymysql.connect(**DB_CONFIG)

    try:
        with conn.cursor() as cursor:
            # 2. 통합 INSERT 처리
            insert_path = os.path.join(QUEUE_DIR, "INSERT_DATA.json")
            if os.path.exists(insert_path):
                print(f"📥 통합 데이터(INSERT) 업로드 시작...")
                with open(insert_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                if data:
                    # 3. Bulk Insert 쿼리 준비
                    sql = """
                          INSERT INTO school_articles
                              (title, content, original_url, created_at, updated_at, vendor_id, category_id)
                          VALUES (%s, %s, %s, %s, %s, %s, %s) 
                          ON DUPLICATE KEY UPDATE 
                              content = VALUES(content);
                              
                          """
                    # 딕셔너리 리스트를 튜플 리스트로 변환
                    values = [
                        (
                            item['title'], item['content'], item['original_url'],
                            item['created_at'], item['updated_at'], item['vendor_id'], item['category_id']
                        )
                        for item in data
                    ]

                    cursor.executemany(sql, values)
                    conn.commit()
                    print(f"   ✅ {len(values)}건 Insert 완료.")

                    # 처리 후 파일 삭제 (옵션)
                    os.remove(insert_path)

            # 3. 통합 UPDATE 처리
            update_path = os.path.join(QUEUE_DIR, "UPDATE_DATA.json")
            if os.path.exists(update_path):
                print(f"🔄 통합 데이터(UPDATE) 처리 시작...")
                with open(update_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                if data:
                    print(f"   ℹ️ {len(data)}건의 데이터가 업데이트 대기 중입니다.")
                    # 개발 보류

                    os.remove(update_path)

    except Exception as e:
        builtins.print(f"❌ DB 업로드 중 치명적 오류: {e}")
    finally:
        conn.close()