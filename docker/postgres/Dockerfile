# INFORM 전용 PostgreSQL 이미지
#
# 공식 postgres 이미지에는 pg_bigm이 없습니다. 한글 2글자 검색(장학, 취업 …)을
# 인덱스로 처리하려면 이 확장이 필요하므로 소스에서 빌드해 넣습니다.
#
# ★ alpine이 아니라 debian 기반을 씁니다.
#   alpine에서 C 확장을 빌드하려면 clang/llvm 버전을 postgres 빌드와 맞춰야 해서
#   깨지기 쉽습니다. 이미지가 ~70MB 커지지만 빌드가 확실합니다.
#
# ★ 로컬 / CI / 프로덕션이 반드시 이 동일한 이미지를 써야 합니다.
#   확장이 없는 환경에서는 Flyway V1이 명시적으로 실패하도록 해두었습니다.

FROM postgres:16

# https://github.com/pgbigm/pg_bigm/releases 에서 최신 태그 확인 후 조정
ARG PG_BIGM_VERSION=1.2-20240606

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        build-essential \
        postgresql-server-dev-16 \
        libicu-dev \
        ca-certificates \
        curl; \
    curl -fsSL -o /tmp/pg_bigm.tar.gz \
        "https://github.com/pgbigm/pg_bigm/archive/refs/tags/v${PG_BIGM_VERSION}.tar.gz"; \
    mkdir -p /tmp/pg_bigm; \
    tar -xzf /tmp/pg_bigm.tar.gz -C /tmp/pg_bigm --strip-components=1; \
    cd /tmp/pg_bigm; \
    make USE_PGXS=1; \
    make USE_PGXS=1 install; \
    cd /; \
    rm -rf /tmp/pg_bigm /tmp/pg_bigm.tar.gz; \
    apt-get purge -y --auto-remove build-essential postgresql-server-dev-16 libicu-dev curl; \
    rm -rf /var/lib/apt/lists/*

# ★ libicu-dev 를 지우면서 런타임 라이브러리(libicu*)까지 날아가면 서버가 뜨지 않는다.
#   PGDG 로 설치된 postgresql-16 이 libicu 를 직접 의존하므로 --auto-remove 대상에서
#   보호되지만, 그게 실제로 성립하는지 빌드 시점에 확인한다.
RUN set -eux; \
    pg_config --version; \
    ls -1 "$(pg_config --pkglibdir)/pg_bigm.so"; \
    ls -1 "$(pg_config --sharedir)/extension/" | grep -E '^pg_bigm'

# 컨테이너 최초 기동 시(데이터 디렉토리가 비어 있을 때) 슈퍼유저로 자동 실행됩니다.
# 확장 설치와 롤 생성은 슈퍼유저 권한이 필요해 Flyway로 처리할 수 없습니다.
COPY initdb/ /docker-entrypoint-initdb.d/
