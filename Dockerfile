FROM python:3.11-slim

# 환경변수 설정
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# 작업 디렉토리 설정
WORKDIR /opt/project

# 필수 시스템 유틸리티 설치
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 5. 파이썬 라이브러리 설치
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Playwright 브라우저 & 의존성 설치
RUN playwright install chromium --with-deps

# 소스 코드 복사
COPY . .

# 실행 명령어
# ENTRYPOINT ["python", "main.py"]