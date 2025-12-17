"""Unified interactive CLI for hedge workflows."""

from __future__ import annotations

import logging
from typing import Callable, Dict

from .common.logging_utils import setup_logging

logger = logging.getLogger(__name__)


def _select_mode() -> str:
    logger.info("\n" + "=" * 60)
    logger.info("헤지 모드 선택")
    logger.info("=" * 60)
    logger.info("1. Step1 - 한국거래소 레드플래그 진입 봇")
    logger.info("2. Step2 - 해외 포지션 청산 (현물+선물)")
    logger.info("3. Step3(수동) - 특정 거래소 선택 (해외 헤지 진입)")
    logger.info("4. Step4 - 김프 청산/포지션 정리 (Exit)")
    logger.info("5. 자동 모드 - 모든 거래소에서 최적 조합 찾기 (해외 헤지 진입)")
    logger.info("0. 종료")
    return input("\n모드 선택 (0-5) [5]: ").strip() or "5"


def main() -> None:
    setup_logging()
    handlers: Dict[str, Callable[[], None]] = {
        "1": _run_step1_redflag_entry,
        "2": _run_step2_overseas_unwind,
        "3": _run_step3_overseas_manual_entry,
        "4": _run_step4_kimchi_exit,
        "5": _run_overseas_auto_entry,
    }

    choice = _select_mode()
    if choice in {"0", "q", "quit", "exit"}:
        return
    handler = handlers.get(choice)
    if not handler:
        logger.error("❌ 올바르지 않은 선택입니다. (0-5)")
        return
    handler()


def _run_overseas_auto_entry() -> None:
    from .overseas.app import run_overseas_entry

    run_overseas_entry(entry_mode="auto")


def _run_step3_overseas_manual_entry() -> None:
    from .overseas.app import run_overseas_entry

    run_overseas_entry(entry_mode="manual")


def _run_step2_overseas_unwind() -> None:
    from .overseas.app import run_overseas_unwind

    run_overseas_unwind()


def _run_step4_kimchi_exit() -> None:
    from .korea.exit.app import main as run_exit

    run_exit()


def _run_step1_redflag_entry() -> None:
    from .korea.redflag.app import main as run_redflag

    run_redflag()
