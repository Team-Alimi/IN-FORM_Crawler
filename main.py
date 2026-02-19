import argparse
import sys
import os
import json
import asyncio

from config import SITES, QUEUE_DIR
from crawlers import TypeACrawler, TypeBCrawler, TypeCCrawler
from dataprepper import Deduplicator, AIProcessor
from common.db_injector import inject_json_to_db


async def get_crawler(site_info):

    if site_info['type'] == 'A':
        crawler = TypeACrawler(site_info)
    elif site_info['type'] == 'B':
        crawler = TypeBCrawler(site_info)
    elif site_info['type'] == 'C':
        crawler = TypeCCrawler(site_info)
    else:
        print(f"⚠️ 알 수 없는 사이트 타입: {site_info['type']}")
        return site_info['name'], []

    return await crawler.run()


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


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--type', required=True, help="크롤러 타입 (A, B...)")
    args = parser.parse_args()
    target_type = args.type.upper()

    print("🚀 [System] 크롤러 실행 시작됨!", flush=True)

    target_sites = [s for s in SITES if s['type'] == target_type]
    if not target_sites:
        print(f"❌ 설정된 사이트가 없습니다: {target_type}")
        sys.exit(1)

    site_count = len(target_sites)

    # === PHASE 1: 크롤링 & JSON 저장 (Async) ===

    MAX_WORKERS_CAP = 8

    max_workers = 1
    raw_data_map = {}

    if site_count <= 8:
        max_workers = site_count
        print(f"⚡ [General Batch] 대상 {site_count}개 -> Async Concurrency {max_workers}")

    else:
        max_workers = MAX_WORKERS_CAP
        print(f"🔥 [Large Batch] 대상 {site_count}개 -> Async Concurrency {max_workers}")

    # Async 실행
    print(f"Waiting for {site_count} tasks to complete...")
    
    sem = asyncio.Semaphore(max_workers)

    async def run_with_sem(site):
        async with sem:
            return await get_crawler(site)

    tasks = [run_with_sem(site) for site in target_sites]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for res in results:
        if isinstance(res, Exception):
            print(f"   🔥 크롤링 에러 발생: {res}")
            continue
            
        site_name, collected_data = res
        if collected_data:
            if site_name not in raw_data_map:
                raw_data_map[site_name] = []
            raw_data_map[site_name].extend(collected_data)
            print(f"   ✅ [{site_name}] 수집 성공: {len(collected_data)}건 (누적: {len(raw_data_map[site_name])}건)")
        else:
            print(f"   ⚠️ [{site_name}] 수집된 데이터 없음")

    # === PHASE 2: 순차 중복 제거 ===
    print(f"\n⚙️ [Phase 2] 중복 제거 및 데이터 분류 시작 (순차 처리)...")

    all_inserts = []
    all_updates = []

    # 수집된 데이터를 하나씩 꺼내서 Deduplicator에게 검사 맡김
    for site_name, data_list in raw_data_map.items():
        if not data_list: continue

        deduper = Deduplicator(site_name)

        inserts, updates = deduper.process_batch(data_list)

        all_inserts.extend(inserts)
        all_updates.extend(updates)

        if len(inserts) > 0 or len(updates) > 0:
            print(f"   👌 [{site_name}] 분류 완료 (신규: {len(inserts)}, 수정: {len(updates)})")

    print(f"[Phase 1] 크롤링 및 중복 제거 완료.")
    print(f"       신규 데이터: {len(all_inserts)}건 / 수정 데이터: {len(all_updates)}건")

    print(f"DEBUG: save_or_clean 호출 시도... (Inserts: {len(all_inserts)})")
    # 통합 파일 저장 (JSON 생성)
    save_or_clean(all_inserts, "INSERT_DATA.json")
    save_or_clean(all_updates, "UPDATE_DATA.json")
    #
    #  # === PHASE 4: DB Bulk Insert ===
    # print(f"🚀 [Phase 2] DB 업로드 시작")
    # inject_json_to_db()

    print(f"🎉 모든 작업 종료.")


if __name__ == "__main__":
    asyncio.run(main())