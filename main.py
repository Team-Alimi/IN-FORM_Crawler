import argparse
import sys
import os
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from webdriver_manager.chrome import ChromeDriverManager

from config import SITES, QUEUE_DIR
from crawlers import TypeACrawler, TypeBCrawler, TypeCCrawler, TypeDCrawler, TypeECrawler
from dataprepper import Deduplicator, AIProcessor
from db_injector import inject_json_to_db


def get_crawler(site_info):

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

    site_count = len(target_sites)

    # 2. 드라이버 사전 설치 (Race Condition 방지)
    print("🔧 Chromedriver 설치 및 경로 확인 중...")
    try:
        # 여기서 딱 한 번만 설치하고 경로를 받아옵니다.
        driver_path = ChromeDriverManager().install()
        print(f"✅ Driver Path: {driver_path}")

        # 모든 사이트 정보에 드라이버 경로를 주입합니다.
        for site in target_sites:
            site['driver_path'] = driver_path

    except Exception as e:
        print(f"❌ 드라이버 초기화 실패: {e}")
        sys.exit(1)

    # === PHASE 1: 크롤링 & JSON 저장 (유동적 스레드 할당) ===

    MAX_WORKERS_CAP = 8

    max_workers = 1
    raw_data_map = {}
    # [조건별 상세 분기 로직]
    if site_count <= 4:
        max_workers = site_count
        print(f"✨ [Small Batch] 대상 {site_count}개 -> 스레드 {max_workers}개 (1:1 즉시 처리)")

    elif site_count < 8:
        max_workers = site_count
        print(f"⚡ [Medium Batch] 대상 {site_count}개 -> 스레드 {max_workers}개 (풀 가동)")

    else:
        max_workers = MAX_WORKERS_CAP
        print(f"🔥 [Large Batch] 대상 {site_count}개 -> 스레드 {max_workers}개 (RAM 보호 제한 적용)")

    # 스레드 풀 실행
    print(f"Waiting for {site_count} tasks to complete...")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 1. 작업을 하나씩 제출하고 '이름표(future)'를 받음
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

    print(f"[Phase 1] 크롤링 및 중복 제거 완료.")
    print(f"       신규 데이터: {len(all_inserts)}건 / 수정 데이터: {len(all_updates)}건")

    # === PHASE 2: AI 기반 카테고리 분류 및 날짜 추출 ===

    if all_inserts:
        ai_processor = AIProcessor()
        all_inserts = ai_processor.process_batch(all_inserts)

    print("[Phase 2] AI 기반 카테고리 분류 및 날짜 추출 완료.")


    # 5. 통합 파일 저장 (JSON 생성)
    save_or_clean(all_inserts, "INSERT_DATA.json")
    save_or_clean(all_updates, "UPDATE_DATA.json")

    #  # === PHASE 3: DB Bulk Insert ===
    # print(f"🚀 [Phase 2] DB 업로드 시작")
    # inject_json_to_db()  # 인자 불필요

    print(f"🎉 모든 작업 종료.")


if __name__ == "__main__":
    main()