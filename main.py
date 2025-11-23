import argparse
import sys
from concurrent.futures import ThreadPoolExecutor
from config import SITES
from crawler import TypeACrawler, TypeBCrawler
from db_injector import inject_json_to_db


def get_crawler(site_info):
    """설정의 type에 따라 적절한 클래스 매핑"""
    if site_info['type'] == 'A':
        return TypeACrawler(site_info)
    elif site_info['type'] == 'B':
        return TypeBCrawler(site_info)
    return None


def run_single_site(site_info):
    crawler = get_crawler(site_info)

    if site_info['type'] == 'A':
        crawler = TypeACrawler(site_info)
    elif site_info['type'] == 'B':
        crawler = TypeBCrawler(site_info)
    else:
        return

    crawler.run()  # run()이 끝나면 JSON 파일이 생성됨


def main():
    # 1. 실행 시 --type 인자를 필수로 받도록 설정
    parser = argparse.ArgumentParser()
    parser.add_argument('--type', required=True, help="실행할 크롤러 타입 (A, B)")
    args = parser.parse_args()
    target_type = args.type.upper()

    # 2. 해당 타입에 맞는 사이트만 필터링 (독립성 보장)
    target_sites = [s for s in SITES if s['type'] == target_type]

    if not target_sites:
        print(f"❌ Type '{target_type}'에 해당하는 사이트 설정이 없습니다.")
        sys.exit(1)

    site_count = len(target_sites)

    # === PHASE 1: 크롤링 & JSON 저장 (유동적 스레드 할당) ===

    MAX_WORKERS_CAP = 8

    max_workers = 1

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
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        executor.map(run_single_site, target_sites)

    print(f"✅ [Phase 1] 크롤링 및 JSON 저장 완료.")

    # # === PHASE 2: DB Bulk Insert ===
    print(f"🚀 [Phase 2] JSON -> DB 일괄 업로드 시작")
    inject_json_to_db(target_sites)

    print(f"🎉 모든 작업 종료.")


if __name__ == "__main__":
    main()