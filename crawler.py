import time
import csv
import re  # 정규 표현식(텍스트에서 패턴을 찾는 강력한 도구)을 위한 라이브러리
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

# 현업에서 사용하는 키워드 분류 리스트
KEYWORDS = ['대회', '공모전', '특강', '강의']
BASE_URL = 'https://www.inha.ac.kr'


def initialize_driver():
    """웹 드라이버를 초기화하고 반환합니다."""
    print("🚀 웹 드라이버 초기화 중...")
    try:
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))
        return driver
    except Exception as e:
        print(f"❌ 드라이버 초기화 실패: {e}")
        return None


def extract_dates_from_content(content):
    """
    본문 내용(content)에서 시작 일시와 마감 일시를 추출합니다.
    (매우 일반적인 패턴인 '일시:', '기간:', '마감일:' 등을 찾아 옆의 텍스트를 가져오는 휴리스틱 사용)
    """
    # 텍스트에서 '일정', '기간', '마감' 등의 키워드를 포함하는 문장을 찾아 시도합니다.

    start_date = "N/A"
    end_date = "N/A"

    # 1. '일정', '기간' 등 주변에서 날짜/시간 패턴을 찾아봅니다.
    # 정규식 수정: (?=\n|$)를 사용하여 뒤에 개행문자가 없어도 매칭되도록 유연하게 만듭니다.
    date_patterns = re.findall(r'(일정|기간|신청기간|마감일|일시)\s*[:：]\s*(.*?)(?=\n|$)', content, re.IGNORECASE)

    for marker, date_str in date_patterns:
        date_str = date_str.strip()

        # 시작/마감 구분 패턴 (예: ~ 또는 -)
        if '~' in date_str or ' - ' in date_str:
            # '~' 또는 ' - ' 기준으로 문자열을 분리
            parts = re.split(r'\s*[~-]\s*', date_str, 1)
            if len(parts) == 2:
                start_date = parts[0].strip()
                end_date = parts[1].strip()
                return start_date, end_date  # 가장 처음 발견된 기간을 사용하고 종료

        # 마감일만 있는 경우
        if ('마감' in marker or '신청기간' in marker) and end_date == "N/A":
            end_date = date_str

        # 시작일만 있는 경우
        if ('시작' in marker or '일시' in marker) and start_date == "N/A":
            start_date = date_str

    return start_date, end_date


def get_article_details(driver, link):
    """개별 게시글 링크에 접속하여 본문 내용과 수정일을 추출합니다."""
    try:
        driver.get(link)
        time.sleep(1)  # 상세 페이지 로딩 대기

        soup = BeautifulSoup(driver.page_source, 'html.parser')

        # 1. 본문 내용 추출 (코드 보강)
        # 사용자가 확인해주신 '.artclView'를 최우선으로 배치합니다.
        selectors = ['.artclView', '.artclViewCont', '.board-content', '#artclViewCont', '.artclViewCont_wrap',
                     '#content_body', '.bbs-view__content']
        content_div = None
        for selector in selectors:
            content_div = soup.select_one(selector)
            if content_div:
                print(f"   (본문: Selector '{selector}'로 성공적으로 찾음)")
                break

        # 추출 실패 시 명확한 오류 메시지 반환
        full_content = content_div.get_text('\n', strip=True) if content_div else "본문 추출 실패: CSS Selector 오류"

        # 2. 작성일, 수정일 추출 (기존 로직 유지)

        # 수정일 추출 로직 (매우 사이트 의존적이며, 없으면 N/A 처리)
        modified_date_tag = soup.find(lambda tag: tag.name == 'span' and '수정일' in tag.get_text())
        if modified_date_tag:
            # 수정일 다음 형제 태그의 텍스트를 가져오거나,
            # 태그 구조를 분석하여 날짜를 추출해야 합니다. 여기서는 간략히 N/A
            modified_date = "N/A (수정일 추출 로직 재확인 필요)"
        else:
            modified_date = "N/A"

        # 3. 일정 추출
        start_date, end_date = extract_dates_from_content(full_content)

        return {
            'content': full_content,
            'start_date': start_date,
            'end_date': end_date,
            'modified_date': modified_date
        }

    except Exception as e:
        print(f"⚠️ 게시글 상세 정보 추출 중 에러 발생 ({link}): {e}")
        return {
            'content': f"상세정보 접근 실패: {e}",
            'start_date': "N/A",
            'end_date': "N/A",
            'modified_date': "N/A"
        }


def crawl_and_classify(driver, target_page_count):
    """페이지를 돌며 목록을 수집하고 분류하여 상세 정보까지 추출합니다."""

    # 중복 체크를 위한 Set (리스트보다 훨씬 빠름)
    seen_links = set()
    final_data = []  # 최종 결과를 담을 리스트

    # 1페이지부터 목표 페이지까지 반복
    for page in range(1, target_page_count + 1):
        print(f"\n====================== {page} 페이지 처리 중 ======================")

        # 1. 페이지 이동 로직 (버튼 클릭 방식 유지)
        if page == 1:
            driver.get(f'{BASE_URL}/kr/950/subview.do')
        else:
            try:
                # 다음 페이지 버튼 클릭 (페이지 숫자로 찾음)
                page_button = driver.find_element(By.XPATH, f'//a[text()="{page}"]')
                print(f"🖱️ {page} 페이지 버튼 클릭...")
                page_button.click()
            except Exception:
                print(f"✅ {page} 페이지 버튼을 찾지 못했습니다. 마지막 페이지입니다.")
                break  # 더 이상 페이지 버튼이 없으면 반복문 종료

        time.sleep(2)  # 페이지 로딩 대기

        # 2. 목록 추출
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        rows = soup.select('tbody tr')

        for row in rows:
            # 기본 목록 데이터 추출
            title_cell = row.select_one('._artclTdTitle') or row.select_one('.title') or row.select_one('.td-subject')
            date_cell = row.select_one('._artclTdRdate') or row.select_one('.td-date')

            if not title_cell: continue

            title = title_cell.get_text(strip=True)
            anchor = title_cell.select_one('a')
            link = BASE_URL + anchor['href'] if anchor else ""
            post_date = date_cell.get_text(strip=True) if date_cell else "N/A"

            # 3. 중복 제거
            if link in seen_links:
                print(f"⏭️ 중복된 글 발견: {title} (건너뛰기)")
                continue
            seen_links.add(link)

            # 4. 분류
            classified_word = "일반"  # 기본값은 일반

            # 제목에서 키워드를 찾아 분류
            for keyword in KEYWORDS:
                if keyword in title:
                    classified_word = keyword
                    break

            # 5. 일반 공지는 여기서 건너뛰고, 키워드 포함 글만 처리
            if classified_word == "일반":
                print(f"➖ 일반 공지: {title} (수집 제외)")
                continue  # 다음 게시물로 넘어감

            # 6. 상세 정보 추출 (키워드에 포함된 경우에만!)
            print(f"➡️ [{classified_word}] 분류됨! 상세 정보 추출 시작: {title}")

            # 상세 정보 추출 함수 호출
            details = get_article_details(driver, link)

            # 추출된 정보 병합
            final_notice = {
                '제목': title,
                '본문 내용': details['content'],
                '사이트 링크': link,
                '일정 시작 일시': details['start_date'],
                '일정 마감 일시': details['end_date'],
                '게시글 작성 일': post_date,
                '게시글 수정 일': details['modified_date'],
                '분류 단어': classified_word
            }
            final_data.append(final_notice)

    return final_data


def save_to_csv(data, filename="inha_classified_notices.csv"):
    """수집된 데이터를 CSV 파일로 저장합니다."""
    print(f"\n\n====================== 데이터 저장 ======================")
    if not data:
        print("저장할 데이터가 없습니다.")
        return

    # 헤더(CSV 컬럼명)는 첫 번째 딕셔너리의 키를 사용
    if data:
        fieldnames = list(data[0].keys())
    else:
        # 데이터가 없을 경우 헤더를 미리 정의
        fieldnames = ['제목', '본문 내용', '사이트 링크', '일정 시작 일시', '일정 마감 일시', '게시글 작성 일', '게시글 수정 일', '분류 단어']

    print(f"💾 총 {len(data)}건의 데이터를 {filename} 파일로 저장하는 중...")

    # 'utf-8-sig'는 엑셀에서 한글 깨짐 방지를 위한 필수 옵션
    with open(filename, mode='w', encoding='utf-8-sig', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)

        writer.writeheader()  # 헤더(컬럼명) 쓰기
        writer.writerows(data)  # 데이터 쓰기

    print("✅ 저장 완료! 프로젝트 폴더를 확인해 보세요.")


# 메인 실행 함수
if __name__ == "__main__":
    driver = initialize_driver()
    if driver:
        try:
            # ⭐⭐⭐ 원하는 페이지 수로 수정하세요. (예: 10페이지) ⭐⭐⭐
            PAGE_LIMIT = 5

            final_data = crawl_and_classify(driver, PAGE_LIMIT)

            save_to_csv(final_data)

        except Exception as e:
            print(f"\n致命的な 에러 발생 (Fatal Error): {e}")

        finally:
            driver.quit()
            print("모든 작업 종료.")