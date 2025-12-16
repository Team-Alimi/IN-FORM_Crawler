import argparse
import sys
import os
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from webdriver_manager.chrome import ChromeDriverManager

from config import SITES, QUEUE_DIR
from crawlers import TypeACrawler, TypeBCrawler, TypeCCrawler, TypeDCrawler, TypeECrawler
from db_injector import inject_json_to_db
# [추가] 우리가 만든 품질 검사원 불러오기
from dataprepper.deduplicate import Deduplicator


def get_crawler(site_info):
    # 크롤러 객체 생성 로직 (기존과 동일)
    if site_info['type'] == 'A':
        crawler = TypeACrawler(site_info)
    elif site_info['type'] == 'B':
        crawler = TypeBCrawler(site_info)
    elif site_info['type'] == 'C':
        crawler = TypeCCrawler(site_info)
    elif site_info['type'] == 'D':
        crawler = TypeDCrawler(site_info)
    elif site_info['type'] == 'E':
        crawler = TypeECrawler(site_info)
    else:
        print(f"⚠️ 알 수 없는 사이트 타입: {site_info['type']}")
        return site_info['name'], []

    # [변경] 이제 run()은 (사이트명, 데이터리스트)를 반환합니다.
    return crawler.run()


def save_or_clean(data, filename):
    file_path = os.path.join(QUEUE_DIR, filename)
    if data:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        print(f"   💾 [Queue] 저장 완료: {filename} ({len(data)}건)")
    else:
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except:
                pass
            print(f"   ℹ️ [Queue] 데이터 없음: {filename}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--type', required=True, help="크롤러 타입 (A, B...)")
    args = parser.parse_args()
    target_type = args.type.upper()

    target_sites = [s for s in SITES if s['type'] == target_type]
    if not target_sites:
        print(f"❌ 설정된 사이트가 없습니다: {target_type}")
        sys.exit(1)

    # 드라이버 설치
    try:
        driver_path = ChromeDriverManager().install()
        for site in target_sites:
            site['driver_path'] = driver_path
    except Exception as e:
        print(f"❌ 드라이버 초기화 실패: {e}")
        sys.exit(1)

    # === PHASE 1: 병렬 크롤링 (속도전) ===
    # 중복 검사를 나중에 하므로, 크롤링은 최대한 빠르게(8스레드) 돌려도 안전합니다.
    max_workers = 8

    # 수집한 데이터를 모아둘 임시 창고
    raw_data_map = {}

    print(f"🔥 [Phase 1] {len(target_sites)}개 사이트 동시 크롤링 시작 (Max Threads: {max_workers})...")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_site = {executor.submit(get_crawler, site): site for site in target_sites}

        for future in as_completed(future_to_site):
            site = future_to_site[future]
            try:
                # 결과 받기: (사이트이름, 수집된데이터)
                site_name, collected_data = future.result()

                if collected_data:
                    raw_data_map[site_name] = collected_data
                    print(f"   ✅ [{site_name}] 수집 성공: {len(collected_data)}건")
                else:
                    print(f"   ⚠️ [{site_name}] 수집된 데이터 없음")

            except Exception as e:
                print(f"   🔥 [{site['name']}] 크롤링 에러: {e}")

    # === PHASE 2: 순차 중복 제거 (안전 제일) ===
    print(f"\n⚙️ [Phase 2] 중복 제거 및 데이터 분류 시작 (순차 처리)...")

    all_inserts = []
    all_updates = []

    # 수집된 데이터를 하나씩 꺼내서 Deduplicator에게 검사 맡김
    for site_name, data_list in raw_data_map.items():
        if not data_list: continue

        # 1. 검사원(Deduplicator) 소환
        deduper = Deduplicator(site_name)

        # 2. 검사 실행 (여기서 GLOBAL_HASH.json을 읽고 씀 -> 순차 실행이라 안전!)
        inserts, updates = deduper.process_batch(data_list)

        all_inserts.extend(inserts)
        all_updates.extend(updates)

        # 로그 출력
        if len(inserts) > 0 or len(updates) > 0:
            print(f"   👌 [{site_name}] 분류 완료 (신규: {len(inserts)}, 수정: {len(updates)})")

    # === PHASE 3: 저장 및 DB 주입 ===
    print(f"\n💾 [Phase 3] 파일 저장 및 DB 업로드...")
    save_or_clean(all_inserts, "INSERT_DATA.json")
    save_or_clean(all_updates, "UPDATE_DATA.json")

    inject_json_to_db()
    print(f"🎉 모든 작업 종료.")


if __name__ == "__main__":
    main()