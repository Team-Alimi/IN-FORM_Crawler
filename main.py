import argparse
import sys
import os
import json
import asyncio

from config import load_sites, QUEUE_DIR
from crawlers import TypeACrawler, TypeBCrawler, TypeCCrawler, TypeDCrawler, TypeECrawler
from common.logger import log_status, init_logger


async def run_crawler(site):
    """사이트 타입별 크롤러 실행"""
    if site['type'] == 'A': c = TypeACrawler(site)
    elif site['type'] == 'B': c = TypeBCrawler(site)
    elif site['type'] == 'C': c = TypeCCrawler(site)
    elif site['type'] == 'D': c = TypeDCrawler(site)
    elif site['type'] == 'E': c = TypeECrawler(site)
    else: return site['name'], []
    return await c.run()

def save_json(data, name):
    """결과 데이터를 JSON 파일로 저장"""
    os.makedirs(QUEUE_DIR, exist_ok=True)
    path = os.path.join(QUEUE_DIR, name)
    if data:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        log_status("System", f"저장 완료: {name} ({len(data)}건)", "SAVE")
    elif os.path.exists(path):
        try: os.remove(path)
        except: pass

async def main():
    """메인 실행 프로세스 제어"""
    p = argparse.ArgumentParser()
    p.add_argument('--type', required=True)
    args = p.parse_args()
    typ = args.type.upper()
    init_logger(args.type)

    log_status("System", f"{typ} 타입 시작", "START")

    targets = load_sites(typ)
    if not targets:
        log_status("System", f"대상 없음 또는 로드 실패: {typ}", "ERROR"); sys.exit(1)

    # === PHASE 1: 비동기 크롤링 수행 ===
    sem = asyncio.Semaphore(min(len(targets), 8))
    async def run_with_sem(s):
        async with sem: return await run_crawler(s)

    results = await asyncio.gather(*[run_with_sem(s) for s in targets], return_exceptions=True)

    raw_map = {}
    for res in results:
        if isinstance(res, Exception): continue
        name, data = res
        if data:
            if name not in raw_map: raw_map[name] = []
            raw_map[name].extend(data)

    # === PHASE 2: 데이터 통합 및 신규/수정 분류 ===
    log_status("System", "데이터 통합 시작", "PHASE")
    all_articles = []
    for name, articles in raw_map.items():
        for a in articles:
            a['site_name'] = name
            all_articles.append(a)

    if all_articles:
        from dataprepper.unifier import Unifier
        inserts, updates = Unifier().unify(all_articles)
    else:
        inserts, updates = [], []

    # === PHASE 3: AI 기반 분류 및 날짜 추출 ===
    if inserts or updates:
        log_status("System", "AI 전처리 시작", "PHASE")
        from dataprepper.ai_engine.base import AI
        ai = AI()
        if inserts: inserts = ai.process(inserts)
        if updates: updates = ai.process(updates)

    # === PHASE 4: 최종 결과 JSON 저장 ===
    inserts = [a for a in inserts if a.get('category_id') != 0]
    updates = [a for a in updates if a.get('category_id') != 0]

    if inserts or updates:
        from dataprepper.unifier import Unifier
        Unifier().commit(inserts, updates)

    log_status("System", f"결과: 신규 {len(inserts)} / 수정 {len(updates)} (분류 미달 제외)", "SUCCESS")
    save_json(inserts, "INSERT_DATA.json")
    save_json(updates, "UPDATE_DATA.json")

    # === PHASE 5: DB 업로드 (Loader 실행) ===
    if inserts or updates:
        log_status("System", "DB 적재 시작", "PHASE")
        from common.db_loader import load_json_to_db
        load_json_to_db()
    
    log_status("System", "전체 공정 완료", "DONE")

if __name__ == "__main__":
    asyncio.run(main())
