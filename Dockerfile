# 1. 파이썬 3.9 슬림 버전
FROM python:3.9-slim

# 2. 필수 시스템 패키지 설치
# (wget, gnupg, unzip, curl 등 설치)
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 3. [수정됨] 구글 크롬 설치 (최신 방식 적용)
# apt-key 대신 gpg 키를 직접 다운로드 받아 저장하는 방식 사용
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# 4. 작업 디렉토리 생성
WORKDIR /app

# 5. 라이브러리 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 6. 소스 코드 전체 복사
COPY . .

# 7. 실행 명령어 (ENTRYPOINT)
ENTRYPOINT ["python", "main.py"]