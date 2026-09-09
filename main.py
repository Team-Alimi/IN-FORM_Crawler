import argparse
import asyncio
import json
import os
import signal
import sys

from common.logger import init_logger, log_status
from common.redaction import sanitize_runtime_artifact
from common.runtime_result import (
    RuntimeConfigurationError,
    RuntimeExitCode,
    classify_runtime_error,
)
from config import QUEUE_DIR, category_code_allows_write, load_sites
from crawlers import (
    TypeACrawler,
    TypeBCrawler,
    TypeCCrawler,
    TypeDCrawler,
    TypeECrawler,
)


class RuntimeInterruption(RuntimeError):
    """Raised when an ephemeral worker must stop without claiming success."""


def _raise_if_interrupted(interruption_event):
    if interruption_event.is_set():
        raise RuntimeInterruption("crawler worker interrupted before success")


async def run_crawler(site):
    """사이트 타입별 크롤러 실행"""
    if site["type"] == "A":
        c = TypeACrawler(site)
    elif site["type"] == "B":
        c = TypeBCrawler(site)
    elif site["type"] == "C":
        c = TypeCCrawler(site)
    elif site["type"] == "D":
        c = TypeDCrawler(site)
    elif site["type"] == "E":
        c = TypeECrawler(site)
    else:
        return site["name"], []
    return await c.run()


def save_json(data, name):
    """결과 데이터를 JSON 파일로 저장"""
    os.makedirs(QUEUE_DIR, exist_ok=True)
    path = os.path.join(QUEUE_DIR, name)
    if data:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(sanitize_runtime_artifact(data), f, ensure_ascii=False, indent=4)
        log_status("System", f"저장 완료: {name} ({len(data)}건)", "SAVE")
    elif os.path.exists(path):
        try:
            os.remove(path)
        except:
            pass


async def main(interruption_event=None):
    """메인 실행 프로세스 제어"""
    interruption_event = interruption_event or asyncio.Event()
    p = argparse.ArgumentParser()
    p.add_argument("--type", required=True)
    args = p.parse_args()
    typ = args.type.upper()
    init_logger(args.type)

    log_status("System", f"{typ} 타입 시작", "START")

    targets = load_sites(typ)
    if not targets:
        log_status("System", f"대상 없음 또는 로드 실패: {typ}", "ERROR")
        raise RuntimeConfigurationError(f"no crawl targets configured for type {typ}")

    # === PHASE 1: 비동기 크롤링 수행 ===
    sem = asyncio.Semaphore(min(len(targets), 8))

    async def run_with_sem(s):
        _raise_if_interrupted(interruption_event)
        async with sem:
            _raise_if_interrupted(interruption_event)
            return await run_crawler(s)

    results = await asyncio.gather(
        *[run_with_sem(s) for s in targets], return_exceptions=True
    )
    _raise_if_interrupted(interruption_event)

    crawler_errors = [result for result in results if isinstance(result, Exception)]
    if crawler_errors:
        log_status("System", f"크롤러 실행 실패: {crawler_errors[0]}", "ERROR")
        raise RuntimeError(
            "하나 이상의 크롤러 실행이 실패했습니다."
        ) from crawler_errors[0]

    raw_map = {}
    for res in results:
        if isinstance(res, Exception):
            continue
        name, data = res
        if data:
            if name not in raw_map:
                raw_map[name] = []
            raw_map[name].extend(data)

    # === PHASE 2: 데이터 통합 및 신규/수정 분류 ===
    log_status("System", "데이터 통합 시작", "PHASE")
    all_articles = []
    for name, articles in raw_map.items():
        for a in articles:
            a["site_name"] = name
            all_articles.append(a)

    if all_articles:
        from dataprepper.unifier import Unifier

        unifier = Unifier()
        inserts, updates = unifier.unify(all_articles)
        log_status(
            "System",
            f"통합 분석 완료 (신규 {len(inserts)} / 수정 {len(updates)})",
            "SUCCESS",
        )
    else:
        unifier = None
        inserts, updates = [], []
        log_status("System", "처리할 데이터 없음", "INFO")

    # === PHASE 3: AI 기반 분류 및 날짜 추출 ===
    if inserts or updates:
        log_status("System", "AI 전처리 시작", "PHASE")
        from dataprepper.ai_engine.base import AI

        ai = AI()
        if inserts:
            inserts = ai.process(inserts)
        if updates:
            updates = ai.process(updates)
    _raise_if_interrupted(interruption_event)

    # === PHASE 4: 최종 결과 JSON 저장 ===
    inserts = [
        article
        for article in inserts
        if category_code_allows_write(article.get("category_code"))
    ]
    updates = [
        article
        for article in updates
        if category_code_allows_write(article.get("category_code"))
    ]
    from common.db_loader import prepare_v11_queue_payload

    insert_payloads = [prepare_v11_queue_payload(article) for article in inserts]
    update_payloads = [prepare_v11_queue_payload(article) for article in updates]

    log_status(
        "System",
        f"결과: 신규 {len(inserts)} / 수정 {len(updates)} (분류 미달 제외)",
        "SUCCESS",
    )
    save_json(insert_payloads, "INSERT_DATA.json")
    save_json(update_payloads, "UPDATE_DATA.json")

    # === PHASE 5: DB 업로드 (Loader 실행) ===
    if inserts or updates:
        _raise_if_interrupted(interruption_event)
        log_status("System", "DB 적재 시작", "PHASE")
        from common.db_loader import load_json_to_db

        load_json_to_db()
        _raise_if_interrupted(interruption_event)
        unifier.commit(inserts, updates)

    log_status("System", "전체 공정 완료", "DONE")


async def run_cli():
    """Forward container termination signals into the safe application boundary."""
    interruption_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    installed_signals = []
    for termination_signal in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(termination_signal, interruption_event.set)
            installed_signals.append(termination_signal)
        except (NotImplementedError, RuntimeError):
            pass

    try:
        await main(interruption_event=interruption_event)
    finally:
        for termination_signal in installed_signals:
            loop.remove_signal_handler(termination_signal)


def run_process():
    """Return the stable application exit code consumed by the AWS worker."""
    try:
        asyncio.run(run_cli())
    except RuntimeInterruption as error:
        log_status("System", str(error), "ERROR")
        return RuntimeExitCode.DETERMINISTIC_APPLICATION_ERROR
    except Exception as error:
        exit_code = classify_runtime_error(error)
        log_status(
            "System",
            f"crawler failed: {type(error).__name__}",
            "ERROR",
        )
        return exit_code
    return RuntimeExitCode.SUCCESS


if __name__ == "__main__":
    raise SystemExit(run_process())
