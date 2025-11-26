import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from webdriver_manager.chrome import ChromeDriverManager

from config import SITES
from crawlers import TypeACrawler, TypeBCrawler, TypeCCrawler, TypeDCrawler, TypeECrawler
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
        print(f"⚠️ 알 수 없는 사이트 타입입니다: {site_info['type']} ({site_info['name']})")
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
        # 1. 작업을 하나씩 제출하고 '이름표(future)'를 받습니다.
        future_to_site = {executor.submit(get_crawler, site): site for site in target_sites}

        # 2. 작업이 끝나는 대로 결과를 확인합니다.
        for future in as_completed(future_to_site):
            site = future_to_site[future]
            try:
                future.result()  # 여기서 스레드 내부 에러가 있으면 재발생(Raise) 시킴
            except Exception as e:
                # 스레드가 숨기고 있던 에러를 메인 화면에 강제로 출력
                print(f"🔥 [{site['name']}] 실행 중 치명적 오류 발생: {e}")

    print(f"✅ [Phase 1] 크롤링 및 JSON 저장 완료.")

    ## === PHASE 2: DB Bulk Insert ===
    print(f"🚀 [Phase 2] JSON -> DB 일괄 업로드 시작")
    inject_json_to_db(target_sites)

    print(f"🎉 모든 작업 종료.")


if __name__ == "__main__":
    main()