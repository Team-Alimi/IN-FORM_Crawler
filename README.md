# INFORM Crawler

> 인하대학교 학내 동아리 및 공식 행사 정보를 한눈에 확인할 수 있는 통합 정보 플랫폼

## 📋 프로젝트 소개

INFORM은 인하대학교 학내의 다양한 동아리 정보와 이벤트를 캘린더 기반으로 제공하는 웹 서비스입니다. 학생들이 관심 있는 동아리와 행사를 쉽게 찾고 참여할 수 있도록 돕습니다.

## 🚀 주요 기능

- **📅 캘린더 뷰**: 월간 캘린더로 모든 행사를 한눈에 확인
- **🎪 이벤트 관리**: 이벤트 목록 조회 및 상세 정보 확인
- **🏛️ 동아리 정보**: 동아리 목록 및 상세 정보 제공
- **🔍 검색 기능**: 원하는 동아리와 행사 빠르게 검색
- **📱 반응형 디자인**: 모바일, 태블릿, 데스크톱 모든 기기 지원

## 🛠️ Crawler 기술 스택

### 🔹 Core Environment
- **Python 3.11**: Asynchronous I/O 기반의 메인 런타임

### 🔹 Crawling Library
- **Scrapy (Type A)**: 정적 웹사이트 대상의 고성능 비동기 크롤러
- **Playwright (Type B, C)**: 동적 렌더링(SPA) 및 브라우저 조작이 필요한 사이트 대응

### 🔹 AI & Processing
- **Upstage Solar Pro 3**: 수집된 게시글의 맥락을 분석하여 카테고리 분류 및 날짜(시작/종료일) 자동 추출

### 🔹 Infrastructure
- **Compute**: GCP Compute Engine (Spot Instance)
- **OS**: Ubuntu 24.04 LTS
- **CI/CD**: GitHub Actions (SSH Deploy)

## 📁 프로젝트 구조

```
IN-FORM_Crawler/
├── .github/ workflows/        # CI/CD 워크플로우
├── common/                    # 공용 유틸리티 및 데이터베이스 주입 모듈
│   ├── db_loader.py           # 통합 데이터를 DB 스키마에 맞춰 Bulk Insert/Update
│   ├── logger.py              # 프로젝트 통합 로깅
│   └── utils.py               # 수집 기한 필터링 및 날짜 정제 로직
├── crawlers/                  # 유형별 수집 엔진 (Type A, B, C)
│   ├── playwright/             # 동적/탭 구조 페이지 대응 (Type B, C)
│   │   ├── base.py              # Playwright 크롤러 공통 부모 클래스
│   │   ├── type_b.py            # Type B 사이트 전용 크롤러
│   │   └── type_c.py            # Type C 사이트 전용 크롤러
│   └── scrapy_app/             # 대량의 정적 목록 페이지 대응 (Type A)
│       ├── spiders/             # 실제 크롤링 봇(Spider)들이 위치하는 곳
│       │   ├── __init__.py
│       │   └── type_a.py        # Type A 사이트 전용 크롤러
│       ├── __init__.py
│       ├── items.py             # 수집할 데이터의 구조(DTO) 정의
│       ├── pipelines.py         # 카테고리 매칭 및 비즈니스 로직 필터링
│       └── settings.py          # Scrapy 설정
├── dataprepper/               # 수집 데이터 후처리 및 분석 엔진
│   ├── ai_engine/              # Solar Pro 3 기반 분류 및 날짜 추출 모듈
│   │   ├── base.py              # AI 분석 배치 실행 및 API 예외 처리
│   │   ├── classifier.py        # 비즈니스 로직에 따른 게시글 카테고리 분류 프롬프트
│   │   └── date_extractor.py    # 자연어 본문에서 시작/종료일을 추출하는 프롬프트
│   ├── deduplicate.py           # 사이트별 히스토리를 관리하여 기수집 데이터의 중복 처리
│   ├── text_cleaner.py          # 불필요한 태그 및 공백을 제거하여 텍스트 정규화 강제
│   └── unifier.py               # 지문 기반 중복 제거 및 다중 출처 통합
├── config.py                  # API Key 및 사이트 목록 전역 설정
├── main.py                    # PHASE 1~4 전체 공정 제어 및 실행 (Entry Point)
└── requirements.txt           # 프로젝트 의존성 목록
```

## 🎯 개발 및 데이터 지침

### 1. 데이터 명명 규칙
- **객체 지칭**: 수집되는 데이터 단위는 항상 `article`로 지칭하며, 고유 ID는 `unique_id`를 사용합니다.
- **출처 관리**: DB 정합성을 위해 단일 ID 대신 배열 구조를 사용합니다.
  - `vendor_ids`: 정수형 배열 (예: `[1, 2]`)
  - `vendor_urls`: 문자열 배열 (예: `["url1", "url2"]`)
  - *ID 기준 오름차순으로 1:1 매칭 정렬*

### 2. 주석 및 로깅 표준
- **의도 중심 주석 (Why)**: "코드가 무엇을 하는지"보다 **"왜 이 로직이 필요한지"** 개발자의 의도를 한국어로 작성합니다.
- **로깅 시스템**: `common/logger.py`를 사용하여 단계별 상태를 가시성 있게 기록합니다. (START, SUCCESS, COLLECT, LINK, PHASE, SAVE, WARN, ERROR, DONE)

### 3. 핵심 수집 로직
- **기한 필터링**: 리소스 최적화를 위해 **현재 기준 n개월**이 지난 게시글은 수집 대상에서 즉시 제외합니다.
- **이미지 기반 지문**: 텍스트가 없는 이미지형 게시물도 `attachments` 필드로 수집하며, 이미지 URL을 포함한 Hash로 데이터 중복을 판별합니다.

### 사전 요구사항 (Prerequisites)

* **Python 3.11** 이상
* **Docker** (로컬 DB 및 배포 환경)
* **Git**

### 설치 및 로컬 세팅 (Installation)

1. 저장소 클론
```bash
git clone https://github.com/Team-Alimi/IN-FORM_Crawler.git
cd IN-FORM_Crawler
```

2. 가상환경 생성 및 활성화 **(권장)**
```bash
python -m venv venv

# Mac/Linux
source venv/bin/activate
# Windows
.\venv\Scripts\activate
```

3. 의존성 설치
```bash
pip install -r requirements.txt
```

4. Playwright 브라우저 설치
*동적 크롤링(Type B, C)을 위한 브라우저 바이너리를 설치합니다.*
```bash
playwright install
```

### ⚙️ 설정 (.env)

**[배포 환경]**
운영 서버 배포 시에는 **GitHub Actions**가 **GitHub Secrets** 값을 이용하여 `.env` 파일을 자동으로 생성합니다.

**[로컬 개발 환경]**
로컬 개발 환경에서는 프로젝트 루트에 `.env` 파일을 직접 생성해야 합니다.

```ini
# Database Config
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_local_password
DB_NAME=informserver

# UPSTAGE AI API (게시글 분류용)
UPSTAGE_AI_API_KEY=your_api_key_here
```

### 🚀 실행

크롤러는 `main.py`를 통해 실행하며, `--type` 인자로 타겟 사이트 유형을 지정합니다.

```bash
# Type A 사이트 크롤링 (Scrapy 기반 정적 수집)
python main.py --type A

# Type B 사이트 크롤링 (Playwright 기반 동적 수집)
python main.py --type B
```

### 🔄 CI/CD Pipeline

이 프로젝트는 **GitHub Actions**를 사용하여 자동 배포됩니다.

1. **Push**: `crawler` 브랜치에 코드가 푸시되면 워크플로우가 트리거됩니다.
2. **Build**: Docker 이미지를 빌드하고 Docker Hub에 업로드합니다.
3. **Deploy**:
* 운영 서버(GCP Instance)에 SSH로 접속합니다.
* GitHub Secrets에 저장된 환경 변수로 서버 내 `.env` 파일을 갱신합니다.
* 최신 Docker 이미지를 Pull 받아 컨테이너를 재시작합니다.

## 🎯 개발 가이드

### Git 컨벤션

- 브랜치, 커밋 메세지는 "type: 간단한 설명"
> 예시: `feat: 로그인 API 구현`

**타입 (Type)**

| 타입 (Type) | 설명 (Description) | 비고 |
| :--- | :--- | :--- |
| **`feat`** | **새로운 기능 추가** | 사용자에게 영향을 주는 새로운 기능 |
| **`fix`** | **버그 수정** | 사용자에게 영향을 주는 버그 수정 |
| **`docs`** | **문서 수정** | README.md, 주석 등 코드 로직과 무관한 문서 변경 |
| **`style`** | **코드 포맷팅** | **비즈니스 로직 변경 없음**. (오타 수정, 탭 사이즈 변경, 세미콜론 누락 등) |
| **`refactor`** | **코드 리팩토링** | 결과는 같으나 코드를 개선함 (변수명 변경, 코드 구조 개선) |
| **`perf`** | **성능 개선** | 실행 시간 단축, 메모리 효율 개선 등 |
| **`test`** | **테스트 코드** | 테스트 코드 추가, 수정, 삭제 (프로덕션 코드 변경 없음) |
| **`build`** | **빌드 시스템, 종속성 변경** | Gradle, npm 패키지 설치/삭제, 설정 파일 변경 |
| **`ci`** | **CI 구성 파일 변경** | GitHub Actions, CircleCI 설정 스크립트 등 |
| **`chore`** | **기타 자잘한 수정** | `.gitignore` 수정, 빌드 스크립트 수정 등 (소스코드 건드리지 않음) |
| **`revert`** | **커밋 되돌리기** | 이전 커밋을 취소할 때 사용 |

## 🔗 vendor_id 목록

### 학교/학과
| 🆔 ID | 🏢 명칭 (Name) | 🔤 이니셜 (Code) | 🏷️ 타입 (Type) |
| :---: | :--- | :---: | :---: |
| 1 | **공과대학** | `IE` | `A` |
| 2 | **기계공학과** | `MEG` | `A` |
| 3 | **항공우주공학과** | `ASE` | `A` |
| 4 | **조선해양공학과** | `NOE` | `A` |
| 5 | **산업경영공학과** | `IEN` | `A` |
| 6 | **화학공학과** | `CHE` | `A` |
| 7 | **고분자공학과** | `PSE` | `A` |
| 8 | **신소재공학과** | `MSE` | `A` |
| 9 | **사회인프라공학과** | `CIV` | `A` |
| 10 | **환경공학과** | `ENV` | `A` |
| 11 | **공간정보공학과** | `GEO` | `A` |
| 12 | **건축학부** | `ARC` | `A` |
| 13 | **에너지자원공학과** | `ENR` | `A` |
| 14 | **전기전자공학부** | `EEC` | `A` |
| 15 | **반도체시스템공학과** | `SSE` | `A` |
| 16 | **소프트웨어융합대학** | `ITCU` | `A` |
| 17 | **인공지능공학과** | `AIEE` | `A` |
| 18 | **데이터사이언스학과** | `DSC` | `A` |
| 19 | **스마트모빌리티공학** | `SME` | `A` |
| 20 | **디자인테크놀로지학과** | `DET` | `A` |
| 21 | **컴퓨터공학과** | `CSE` | `A` |
| 22 | **소프트웨어중심대학사업단** | `SWU` | `A` |
| 23 | **이차전지융합학과** | `IB` | `A` |
| 24 | **자연과학대학** | `INS` | `A` |
| 25 | **수학과** | `MTH` | `A` |
| 26 | **통계학과** | `STS` | `A` |
| 27 | **물리학과** | `PHY` | `A` |
| 28 | **화학학과** | `CHM` | `A` |
| 29 | **해양과학과** | `OCN` | `A` |
| 30 | **식품영양학과** | `IFN` | `A` |
| 31 | **바이오시스템융합학부** | `BIO` | `A` |
| 32 | **생명공학과** | `IBE` | `A` |
| 33 | **바이오제약공학과** | `BPH` | `A` |
| 34 | **생명과학과** | `IBG` | `A` |
| 35 | **첨단바이오의약학과** | `BMD` | `A` |
| 36 | **이차전지공학(융합전공)** | `IBF` | `B` |
| 37 | **반도체공학(융합전공)** | `SEF` | `C` |
| 38 | **인하공학교육혁신센터** | `ICEE` | `A` |

## 📝 License

![MIT License](https://img.shields.io/badge/License-MIT-green.svg?style=for-the-badge&logo=license&logoColor=white)

본 프로젝트의 소스 코드는 **MIT License**를 따릅니다.

> **⚠️**
> 단, 크롤링 대상 사이트(**인하대학교 및 산하 기관**)의 콘텐츠(게시글, 이미지 등)에 대한 모든 권리는 해당 저작권자에게 있습니다.

## 👥 Contact

**Team Alimi**에게 전하고 싶은 말씀이 있으신가요? 목적에 맞게 아래 채널로 연락해 주세요!

| **분류 (Category)** | **채널 (Channel)** |
| :--- | :--- |
| 🐛 **버그 제보  기능 요청** | [**GitHub Issues**](../../issues) |
| 📧 **기타 문의사항** | [**team.alimi.inform@gmail.com**](mailto:team.alimi.inform@gmail.com) |

[![GitHub Issues](https://img.shields.io/badge/GitHub%20Issues-Bug%20Report%20%26%20Feature%20Request-green?style=for-the-badge&logo=github)](../../issues)
[![Email](https://img.shields.io/badge/Team%20Alimi-team.alimi.inform%40gmail.com-EA4335?style=for-the-badge&logo=gmail&logoColor=white)](mailto:team.alimi.inform@gmail.com)
