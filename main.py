import argparse
import sys
import os
import json
import asyncio

from config import SITES, QUEUE_DIR
from crawlers import TypeACrawler, TypeBCrawler, TypeCCrawler
from common.logger import log_status

async def launch_crawler(site_info):
    """사이트 타입에 맞는 크롤러 실행"""
    if site_info['type'] == 'A': crawler = TypeACrawler(site_info)
    elif site_info['type'] == 'B': crawler = TypeBCrawler(site_info)
    elif site_info['type'] == 'C': crawler = TypeCCrawler(site_info)
    else: return site_info['name'], []
    return await crawler.run()

def export_articles_to_json(article_list, filename):
    """수집 데이터를 JSON으로 저장하거나 데이터가 없으면 기존 파일 삭제"""
    os.makedirs(QUEUE_DIR, exist_ok=True)
    file_path = os.path.join(QUEUE_DIR, filename)

    if article_list:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(article_list, f, ensure_ascii=False, indent=4)
        log_status("System", f"데이터 저장 완료: {filename} ({len(article_list)}건)", "SAVE")
    else:
        if os.path.exists(file_path):
            try: os.remove(file_path)
            except: pass

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--type', required=True, help="크롤러 타입 (A, B, C...)")
    args = parser.parse_args()
    target_type = args.type.upper()

    log_status("System", f"{target_type} 타입 크롤러 시작", "START")

    target_sites = [s for s in SITES if s['type'] == target_type]
    if not target_sites:
        log_status("System", f"설정된 사이트 없음: {target_type}", "ERROR")
        sys.exit(1)

    # === PHASE 1: 비동기 크롤링 수행 ===
    max_workers = min(len(target_sites), 8)
    sem = asyncio.Semaphore(max_workers)

    async def run_with_sem(site):
        async with sem: return await launch_crawler(site)

    tasks = [run_with_sem(site) for site in target_sites]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    raw_data_map = {}
    for res in results:
        if isinstance(res, Exception): continue
        site_name, collected_articles = res
        if collected_articles:
            if site_name not in raw_data_map: raw_data_map[site_name] = []
            raw_data_map[site_name].extend(collected_articles)

    # === PHASE 2: 데이터 통합 및 신규/수정 분류 ===
    log_status("System", "데이터 통합 및 분류 시작", "PHASE")

    all_articles = []
    for site_name, article_list in raw_data_map.items():
        for article in article_list:
            article['site_name'] = site_name
            all_articles.append(article)

    if all_articles:
        from dataprepper.unifier import DataUnifier
        unifier = DataUnifier()
        final_inserts, final_updates = unifier.unify_collected_articles(all_articles)
    else:
        final_inserts, final_updates = [], []

    log_status("System", f"결과: 신규(INSERT) {len(final_inserts)}건 / 수정(UPDATE) {len(final_updates)}건", "SUCCESS")

    # 결과물 저장
    export_articles_to_json(final_inserts, "INSERT_DATA.json")
    export_articles_to_json(final_updates, "UPDATE_DATA.json")

    log_status("System", "모든 작업 완료", "DONE")

if __name__ == "__main__":
    asyncio.run(main())
