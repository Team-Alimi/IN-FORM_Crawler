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
- **Google Gemini 2.5 Flash**: 게시글 내용을 분석하여 카테고리 태깅 및 일정 추출

### 🔹 Infrastructure
- **Compute**: GCP Compute Engine (Spot Instance)
- **OS**: Ubuntu 24.04 LTS
- **CI/CD**: GitHub Actions (SSH Deploy)

## 📁 프로젝트 구조

```
IN-FORM_Crawler/
├── .github/
│   └── workflows/
│       └── crawler_deploy.yml   # GitHub Actions CI/CD 워크플로우 설정
├── common/                      # 프로젝트 전반에 사용되는 공용 모듈
│   ├── __init__.py
│   └── db_injector.py           # 수집된 데이터를 메인 DB로 전송하는 모듈
├── crawlers/                    # 크롤링 핵심 로직 패키지
│   ├── playwright/              # Playwright 기반 크롤러 (동적/복잡한 페이지용)
│   │   ├── __init__.py
│   │   ├── base.py              # Playwright 크롤러 공통 부모 클래스
│   │   ├── type_b.py            # Type B 사이트 전용 크롤러
│   │   └── type_c.py            # Type C 사이트 전용 크롤러
│   └── scrapy_app/              # Scrapy 기반 크롤러 (정적/대량 페이지용)
│       ├── spiders/             # 실제 크롤링 봇(Spider)들이 위치하는 곳
│       │   ├── __init__.py
│       │   └── type_a.py        # Type A 사이트 전용 크롤러
│       ├── __init__.py
│       ├── items.py             # 수집할 데이터의 구조(DTO) 정의
│       ├── middlewares.py       # 요청/응답 중간 처리
│       ├── pipelines.py         # 카테고리 매칭 및 비즈니스 로직 필터링
│       ├── settings.py          # Scrapy 설정
│       └── utils.py             # 날짜 포맷 변환 등 순수 유틸리티 함수
├── config.py                    # 환경 변수 및 전역 설정 관리
├── Dockerfile                   # Docker 이미지 빌드 명세서
├── main.py                      # 프로그램 실행 진입점 (Entry Point)
├── requirements.txt             # Python 의존성 라이브러리 목록
└── scrapy.cfg                   # Scrapy 프로젝트 식별 및 배포 설정 파일
```

## 🚦 시작하기

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

# Gemini API (게시글 분류용)
GEMINI_API_KEY=your_api_key_here
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

### 동아리

| 🆔 ID | 🏢 명칭 (Name) | 🔤 이니셜 (Code) | 🏷️ 타입 (Type) |
| :---: | :--- | :---: | :---: |
| 101 | **추가예정** | `COMING` | `SOON` |

## 👥 Contact

team.alimi.inform@gmail.com

