import os
import json
import pymysql
from config import DB_CONFIG, DATA_DIR


def inject_json_to_db(target_sites):
    """
    지정된 사이트들의 JSON 파일을 읽어서 DB에 Bulk Insert 수행
    target_sites: main.py에서 넘겨준 사이트 정보 리스트
    """
    # 1. DB 연결 (한 번만 연결해서 재사용)
    conn = pymysql.connect(**DB_CONFIG)

    try:
        with conn.cursor() as cursor:
            for site in target_sites:
                file_path = os.path.join(DATA_DIR, f"{site['name']}.json")

                # 파일이 없으면 스킵 (수집된 게 없거나 에러난 경우)
                if not os.path.exists(file_path):
                    continue

                print(f"📥 [{site['name']}] DB 업로드 시작...")

                # 2. JSON 파일 읽기
                with open(file_path, 'r', encoding='utf-8') as f:
                    articles = json.load(f)

                if not articles:
                    continue

                # 3. Bulk Insert 쿼리 준비
                sql = """
                      INSERT INTO school_articles
                          (title, content, original_url, created_at, updated_at, vendor_id, category)
                      VALUES (%s, %s, %s, %s, %s, %s) \
                      """

                # 딕셔너리 리스트를 튜플 리스트로 변환
                values = [
                    (
                        a['title'], a['content'], a['original_url'],
                        a['created_at'], a['updated_at'], a['vendor_id'],a['category']
                    )
                    for a in articles
                ]

                # 4. 실행 (executemany로 한방에 넣기)
                cursor.executemany(sql, values)
                conn.commit()

                print(f"✅ [{site['name']}] {len(values)}건 업로드 완료.")

                # (선택사항) 처리된 파일 삭제 or 백업 폴더로 이동
                # os.remove(file_path)

    except Exception as e:
        print(f"❌ DB 업로드 중 치명적 오류: {e}")
    finally:
        conn.close()